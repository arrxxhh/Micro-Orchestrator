#include "http_server.h"
#include <sstream>
#include <algorithm>
#include <cstring>

HttpServer::HttpServer(NodeAgent& agent, int port) : agent(agent), port(port), running(false) {
    server_socket = -1;
}

HttpServer::~HttpServer() {
    stop_server();
}

bool HttpServer::start_server() {
    // Create socket
    server_socket = socket(AF_INET, SOCK_STREAM, 0);
    if (server_socket < 0) {
        std::cerr << "Error creating HTTP server socket" << std::endl;
        return false;
    }
    
    // Set socket options
    int opt = 1;
    if (setsockopt(server_socket, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt)) < 0) {
        std::cerr << "Error setting HTTP server socket options" << std::endl;
        return false;
    }
    
    // Bind socket
    struct sockaddr_in server_addr;
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(port);
    
    if (bind(server_socket, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
        std::cerr << "Error binding HTTP server socket" << std::endl;
        return false;
    }
    
    // Listen for connections
    if (listen(server_socket, 10) < 0) {
        std::cerr << "Error listening on HTTP server socket" << std::endl;
        return false;
    }
    
    running = true;
    std::cout << "HTTP Server started on port " << port << std::endl;
    return true;
}

void HttpServer::stop_server() {
    running = false;
    if (server_socket >= 0) {
        close(server_socket);
        server_socket = -1;
    }
}

void HttpServer::run_server() {
    while (running) {
        struct sockaddr_in client_addr;
        socklen_t client_len = sizeof(client_addr);
        
        int client_socket = accept(server_socket, (struct sockaddr*)&client_addr, &client_len);
        if (client_socket < 0) {
            if (running) {
                std::cerr << "Error accepting HTTP connection" << std::endl;
            }
            continue;
        }
        
        // Handle client in a separate thread
        std::thread client_thread(&HttpServer::handle_client, this, client_socket);
        client_thread.detach();
    }
}

void HttpServer::handle_client(int client_socket) {
    std::string request = read_request(client_socket);
    if (request.empty()) {
        close(client_socket);
        return;
    }
    
    // Parse HTTP request
    std::istringstream request_stream(request);
    std::string method, path, version;
    request_stream >> method >> path >> version;
    
    // Read headers
    std::string line;
    std::map<std::string, std::string> headers;
    while (std::getline(request_stream, line) && line != "\r" && line != "") {
        if (line.back() == '\r') line.pop_back();
        if (line.empty()) break;
        
        size_t colon_pos = line.find(':');
        if (colon_pos != std::string::npos) {
            std::string key = line.substr(0, colon_pos);
            std::string value = line.substr(colon_pos + 1);
            // Trim whitespace
            value.erase(0, value.find_first_not_of(" \t"));
            value.erase(value.find_last_not_of(" \t") + 1);
            headers[key] = value;
        }
    }
    
    // Read body
    std::string body;
    if (headers.find("Content-Length") != headers.end()) {
        int content_length = std::stoi(headers["Content-Length"]);
        char* buffer = new char[content_length + 1];
        int bytes_read = recv(client_socket, buffer, content_length, 0);
        if (bytes_read > 0) {
            buffer[bytes_read] = '\0';
            body = std::string(buffer);
        }
        delete[] buffer;
    }
    
    // Route request
    std::string response;
    if (method == "GET" && path == "/status") {
        response = handle_status_request();
    } else if (method == "POST" && path == "/start") {
        response = handle_start_request(body);
    } else if (method == "POST" && path == "/stop") {
        response = handle_stop_request(body);
    } else {
        response = create_error_response("Not Found", 404);
    }
    
    send_response(client_socket, response);
    close(client_socket);
}

std::string HttpServer::read_request(int client_socket) {
    char buffer[4096];
    std::string request;
    
    while (true) {
        memset(buffer, 0, sizeof(buffer));
        int bytes_received = recv(client_socket, buffer, sizeof(buffer) - 1, 0);
        
        if (bytes_received <= 0) {
            break;
        }
        
        request += std::string(buffer, bytes_received);
        
        // Check if we've received the complete request
        if (request.find("\r\n\r\n") != std::string::npos) {
            break;
        }
    }
    
    return request;
}

void HttpServer::send_response(int client_socket, const std::string& response) {
    send(client_socket, response.c_str(), response.length(), 0);
}

std::string HttpServer::create_json_response(const std::string& data, int status_code) {
    std::string status_text;
    switch (status_code) {
        case 200: status_text = "OK"; break;
        case 400: status_text = "Bad Request"; break;
        case 404: status_text = "Not Found"; break;
        case 500: status_text = "Internal Server Error"; break;
        default: status_text = "Unknown"; break;
    }
    
    std::ostringstream response;
    response << "HTTP/1.1 " << status_code << " " << status_text << "\r\n";
    response << "Content-Type: application/json\r\n";
    response << "Content-Length: " << data.length() << "\r\n";
    response << "Access-Control-Allow-Origin: *\r\n";
    response << "Access-Control-Allow-Methods: GET, POST, DELETE\r\n";
    response << "Access-Control-Allow-Headers: Content-Type\r\n";
    response << "\r\n";
    response << data;
    
    return response.str();
}

std::string HttpServer::create_error_response(const std::string& error, int status_code) {
    std::ostringstream json;
    json << "{\"error\":\"" << error << "\"}";
    return create_json_response(json.str(), status_code);
}

std::string HttpServer::handle_status_request() {
    SystemMetrics metrics = agent.get_system_metrics();
    std::vector<ProcessInfo> processes = agent.get_running_processes();
    
    std::ostringstream json;
    json << "{";
    json << "\"cpu_usage\":" << metrics.cpu_usage << ",";
    json << "\"memory_usage\":" << metrics.memory_usage << ",";
    json << "\"total_memory\":" << metrics.total_memory << ",";
    json << "\"available_memory\":" << metrics.available_memory << ",";
    json << "\"running_processes\":" << processes.size() << ",";
    json << "\"processes\":[";
    
    for (size_t i = 0; i < processes.size(); ++i) {
        if (i > 0) json << ",";
        json << "{";
        json << "\"pid\":" << processes[i].pid << ",";
        json << "\"command\":\"" << processes[i].command << "\",";
        json << "\"start_time\":\"" << processes[i].start_time << "\",";
        json << "\"status\":\"" << processes[i].status << "\"";
        json << "}";
    }
    
    json << "]}";
    
    return create_json_response(json.str());
}

std::string HttpServer::handle_start_request(const std::string& body) {
    std::string script_path = parse_json_field(body, "script_path");
    if (script_path.empty()) {
        return create_error_response("Missing script_path field", 400);
    }
    
    pid_t pid = agent.start_process(script_path);
    if (pid > 0) {
        std::ostringstream json;
        json << "{\"pid\":" << pid << ",\"status\":\"started\"}";
        return create_json_response(json.str());
    } else {
        return create_error_response("Failed to start process", 500);
    }
}

std::string HttpServer::handle_stop_request(const std::string& body) {
    std::string pid_str = parse_json_field(body, "pid");
    if (pid_str.empty()) {
        return create_error_response("Missing pid field", 400);
    }
    
    try {
        pid_t pid = std::stoi(pid_str);
        if (agent.stop_process(pid)) {
            std::ostringstream json;
            json << "{\"status\":\"stopped\"}";
            return create_json_response(json.str());
        } else {
            return create_error_response("Failed to stop process", 500);
        }
    } catch (const std::exception& e) {
        return create_error_response("Invalid PID format", 400);
    }
}

std::string HttpServer::parse_json_field(const std::string& json, const std::string& field) {
    std::string pattern = "\"" + field + "\":";
    size_t pos = json.find(pattern);
    if (pos == std::string::npos) {
        return "";
    }
    
    pos += pattern.length();
    
    // Skip whitespace
    while (pos < json.length() && (json[pos] == ' ' || json[pos] == '\t')) {
        pos++;
    }
    
    if (pos >= json.length()) {
        return "";
    }
    
    // Handle string values
    if (json[pos] == '"') {
        pos++; // Skip opening quote
        size_t end_pos = json.find('"', pos);
        if (end_pos == std::string::npos) {
            return "";
        }
        return json.substr(pos, end_pos - pos);
    }
    
    // Handle numeric values
    size_t end_pos = pos;
    while (end_pos < json.length() && 
           (std::isdigit(json[end_pos]) || json[end_pos] == '.' || json[end_pos] == '-')) {
        end_pos++;
    }
    
    return json.substr(pos, end_pos - pos);
} 