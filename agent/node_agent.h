#ifndef NODE_AGENT_H
#define NODE_AGENT_H

#include <iostream>
#include <map>
#include <string>
#include <vector>
#include <thread>
#include <mutex>
#include <atomic>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <sys/wait.h>
#include <signal.h>
#include <fstream>
#include <sstream>
#include <cstring>
#include <memory>

// System metrics structure
struct SystemMetrics
{
    double cpu_usage;
    double memory_usage;
    long total_memory;
    long available_memory;
    int running_processes;
};

// Process information structure
struct ProcessInfo
{
    pid_t pid;
    std::string command;
    std::string start_time;
    std::string status;
};

class NodeAgent
{
private:
    int server_socket;
    int port;
    std::atomic<bool> running;
    std::map<pid_t, ProcessInfo> running_processes;
    std::mutex processes_mutex;

    // CPU metrics tracking
    long prev_total_time;
    long prev_idle_time;

    // Thread pool for handling multiple clients
    std::vector<std::thread> worker_threads;
    static const int MAX_THREADS = 10;

public:
    NodeAgent(int port = 8080);
    ~NodeAgent();

    // Main server functions
    bool start_server();
    void stop_server();
    void run_server();

    // Process management
    pid_t start_process(const std::string &script_path);
    bool stop_process(pid_t pid);
    std::vector<ProcessInfo> get_running_processes();

    // Metrics collection
    SystemMetrics get_system_metrics();
    double calculate_cpu_usage();
    double calculate_memory_usage();

    // Command handling
    std::string handle_command(const std::string &command);
    std::string handle_start_command(const std::vector<std::string> &args);
    std::string handle_stop_command(const std::vector<std::string> &args);
    std::string handle_status_command();

    // Utility functions
    std::vector<std::string> split_string(const std::string &str, char delimiter);
    std::string get_current_time();
    void cleanup_zombie_processes();

    // Client connection handling
    void handle_client(int client_socket);
    void worker_thread_function();
};

#endif // NODE_AGENT_H