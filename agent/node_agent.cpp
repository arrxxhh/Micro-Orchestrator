#include "node_agent.h"
#include <chrono>
#include <iomanip>
#include <ctime>

NodeAgent::NodeAgent(int port) : port(port), running(false), prev_total_time(0), prev_idle_time(0) {
    server_socket = -1;
}

NodeAgent::~NodeAgent() {
    stop_server();
}

bool NodeAgent::start_server() {
    // Create socket
    server_socket = socket(AF_INET, SOCK_STREAM, 0);
    if (server_socket < 0) {
        std::cerr << "Error creating socket" << std::endl;
        return false;
    }
    
    // Set socket options
    int opt = 1;
    if (setsockopt(server_socket, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt)) < 0) {
        std::cerr << "Error setting socket options" << std::endl;
        return false;
    }
    
    // Bind socket
    struct sockaddr_in server_addr;
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(port);
    
    if (bind(server_socket, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
        std::cerr << "Error binding socket" << std::endl;
        return false;
    }
    
    // Listen for connections
    if (listen(server_socket, 10) < 0) {
        std::cerr << "Error listening on socket" << std::endl;
        return false;
    }
    
    running = true;
    std::cout << "Node Agent started on port " << port << std::endl;
    return true;
}

void NodeAgent::stop_server() {
    running = false;
    if (server_socket >= 0) {
        close(server_socket);
        server_socket = -1;
    }
    
    // Wait for worker threads to finish
    for (auto& thread : worker_threads) {
        if (thread.joinable()) {
            thread.join();
        }
    }
    worker_threads.clear();
}

void NodeAgent::run_server() {
    // Start worker threads
    for (int i = 0; i < MAX_THREADS; ++i) {
        worker_threads.emplace_back(&NodeAgent::worker_thread_function, this);
    }
    
    while (running) {
        struct sockaddr_in client_addr;
        socklen_t client_len = sizeof(client_addr);
        
        int client_socket = accept(server_socket, (struct sockaddr*)&client_addr, &client_len);
        if (client_socket < 0) {
            if (running) {
                std::cerr << "Error accepting connection" << std::endl;
            }
            continue;
        }
        
        // Handle client in a separate thread
        std::thread client_thread(&NodeAgent::handle_client, this, client_socket);
        client_thread.detach();
    }
}

void NodeAgent::handle_client(int client_socket) {
    char buffer[1024];
    while (running) {
        memset(buffer, 0, sizeof(buffer));
        int bytes_received = recv(client_socket, buffer, sizeof(buffer) - 1, 0);
        
        if (bytes_received <= 0) {
            break;
        }
        
        std::string command(buffer);
        std::string response = handle_command(command);
        
        send(client_socket, response.c_str(), response.length(), 0);
    }
    
    close(client_socket);
}

void NodeAgent::worker_thread_function() {
    // Worker threads are used for background tasks like metrics collection
    while (running) {
        cleanup_zombie_processes();
        std::this_thread::sleep_for(std::chrono::seconds(5));
    }
}

std::string NodeAgent::handle_command(const std::string& command) {
    std::vector<std::string> args = split_string(command, ' ');
    if (args.empty()) {
        return "ERROR: Empty command";
    }
    
    std::string cmd = args[0];
    
    if (cmd == "START") {
        return handle_start_command(args);
    } else if (cmd == "STOP") {
        return handle_stop_command(args);
    } else if (cmd == "STATUS") {
        return handle_status_command();
    } else {
        return "ERROR: Unknown command: " + cmd;
    }
}

std::string NodeAgent::handle_start_command(const std::vector<std::string>& args) {
    if (args.size() < 2) {
        return "ERROR: START command requires script path";
    }
    
    std::string script_path = args[1];
    pid_t pid = start_process(script_path);
    
    if (pid > 0) {
        return "SUCCESS: Process started with PID " + std::to_string(pid);
    } else {
        return "ERROR: Failed to start process";
    }
}

std::string NodeAgent::handle_stop_command(const std::vector<std::string>& args) {
    if (args.size() < 2) {
        return "ERROR: STOP command requires PID";
    }
    
    try {
        pid_t pid = std::stoi(args[1]);
        if (stop_process(pid)) {
            return "SUCCESS: Process " + std::to_string(pid) + " stopped";
        } else {
            return "ERROR: Failed to stop process " + std::to_string(pid);
        }
    } catch (const std::exception& e) {
        return "ERROR: Invalid PID format";
    }
}

std::string NodeAgent::handle_status_command() {
    SystemMetrics metrics = get_system_metrics();
    std::vector<ProcessInfo> processes = get_running_processes();
    
    std::stringstream response;
    response << "STATUS:\n";
    response << "CPU Usage: " << std::fixed << std::setprecision(2) << metrics.cpu_usage << "%\n";
    response << "Memory Usage: " << std::fixed << std::setprecision(2) << metrics.memory_usage << "%\n";
    response << "Total Memory: " << metrics.total_memory << " KB\n";
    response << "Available Memory: " << metrics.available_memory << " KB\n";
    response << "Running Processes: " << processes.size() << "\n\n";
    
    response << "Processes:\n";
    for (const auto& proc : processes) {
        response << "PID: " << proc.pid << " | Command: " << proc.command 
                << " | Started: " << proc.start_time << " | Status: " << proc.status << "\n";
    }
    
    return response.str();
}

pid_t NodeAgent::start_process(const std::string& script_path) {
    pid_t pid = fork();
    
    if (pid == 0) {
        // Child process
        execlp(script_path.c_str(), script_path.c_str(), nullptr);
        exit(1); // Only reached if exec fails
    } else if (pid > 0) {
        // Parent process
        std::lock_guard<std::mutex> lock(processes_mutex);
        
        ProcessInfo info;
        info.pid = pid;
        info.command = script_path;
        info.start_time = get_current_time();
        info.status = "RUNNING";
        
        running_processes[pid] = info;
        return pid;
    } else {
        // Fork failed
        return -1;
    }
}

bool NodeAgent::stop_process(pid_t pid) {
    std::lock_guard<std::mutex> lock(processes_mutex);
    
    auto it = running_processes.find(pid);
    if (it == running_processes.end()) {
        return false;
    }
    
    // Send SIGTERM first
    if (kill(pid, SIGTERM) == 0) {
        // Wait a bit for graceful shutdown
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
        
        // Check if process is still running
        if (kill(pid, 0) == 0) {
            // Force kill with SIGKILL
            kill(pid, SIGKILL);
        }
        
        running_processes.erase(it);
        return true;
    }
    
    return false;
}

std::vector<ProcessInfo> NodeAgent::get_running_processes() {
    std::lock_guard<std::mutex> lock(processes_mutex);
    std::vector<ProcessInfo> result;
    
    for (const auto& pair : running_processes) {
        result.push_back(pair.second);
    }
    
    return result;
}

SystemMetrics NodeAgent::get_system_metrics() {
    SystemMetrics metrics;
    metrics.cpu_usage = calculate_cpu_usage();
    metrics.memory_usage = calculate_memory_usage();
    
    // Get memory info
    std::ifstream meminfo("/proc/meminfo");
    if (meminfo.is_open()) {
        std::string line;
        while (std::getline(meminfo, line)) {
            if (line.find("MemTotal:") == 0) {
                sscanf(line.c_str(), "MemTotal: %ld", &metrics.total_memory);
            } else if (line.find("MemAvailable:") == 0) {
                sscanf(line.c_str(), "MemAvailable: %ld", &metrics.available_memory);
            }
        }
    }
    
    std::lock_guard<std::mutex> lock(processes_mutex);
    metrics.running_processes = running_processes.size();
    
    return metrics;
}

double NodeAgent::calculate_cpu_usage() {
    std::ifstream stat_file("/proc/stat");
    if (!stat_file.is_open()) {
        return 0.0;
    }
    
    std::string line;
    if (std::getline(stat_file, line)) {
        long user, nice, system, idle, iowait, irq, softirq, steal;
        sscanf(line.c_str(), "cpu %ld %ld %ld %ld %ld %ld %ld %ld",
               &user, &nice, &system, &idle, &iowait, &irq, &softirq, &steal);
        
        long total_time = user + nice + system + idle + iowait + irq + softirq + steal;
        long idle_time = idle + iowait;
        
        if (prev_total_time > 0) {
            long total_diff = total_time - prev_total_time;
            long idle_diff = idle_time - prev_idle_time;
            
            if (total_diff > 0) {
                double cpu_usage = 100.0 * (1.0 - (double)idle_diff / total_diff);
                prev_total_time = total_time;
                prev_idle_time = idle_time;
                return cpu_usage;
            }
        }
        
        prev_total_time = total_time;
        prev_idle_time = idle_time;
    }
    
    return 0.0;
}

double NodeAgent::calculate_memory_usage() {
    std::ifstream meminfo("/proc/meminfo");
    if (!meminfo.is_open()) {
        return 0.0;
    }
    
    long total_memory = 0;
    long available_memory = 0;
    std::string line;
    
    while (std::getline(meminfo, line)) {
        if (line.find("MemTotal:") == 0) {
            sscanf(line.c_str(), "MemTotal: %ld", &total_memory);
        } else if (line.find("MemAvailable:") == 0) {
            sscanf(line.c_str(), "MemAvailable: %ld", &available_memory);
        }
    }
    
    if (total_memory > 0) {
        return 100.0 * (1.0 - (double)available_memory / total_memory);
    }
    
    return 0.0;
}

std::vector<std::string> NodeAgent::split_string(const std::string& str, char delimiter) {
    std::vector<std::string> tokens;
    std::stringstream ss(str);
    std::string token;
    
    while (std::getline(ss, token, delimiter)) {
        if (!token.empty()) {
            tokens.push_back(token);
        }
    }
    
    return tokens;
}

std::string NodeAgent::get_current_time() {
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    std::stringstream ss;
    ss << std::put_time(std::localtime(&time_t), "%Y-%m-%d %H:%M:%S");
    return ss.str();
}

void NodeAgent::cleanup_zombie_processes() {
    std::lock_guard<std::mutex> lock(processes_mutex);
    
    auto it = running_processes.begin();
    while (it != running_processes.end()) {
        pid_t pid = it->first;
        
        // Check if process is still running
        if (kill(pid, 0) != 0) {
            // Process is no longer running
            it = running_processes.erase(it);
        } else {
            ++it;
        }
    }
} 