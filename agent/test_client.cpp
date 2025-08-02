#include <iostream>
#include <string>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>

class TestClient {
private:
    int sock;
    std::string host;
    int port;

public:
    TestClient(const std::string& host = "localhost", int port = 8080) 
        : host(host), port(port), sock(-1) {}
    
    ~TestClient() {
        if (sock >= 0) {
            close(sock);
        }
    }
    
    bool connect() {
        sock = socket(AF_INET, SOCK_STREAM, 0);
        if (sock < 0) {
            std::cerr << "Error creating socket" << std::endl;
            return false;
        }
        
        struct sockaddr_in server_addr;
        server_addr.sin_family = AF_INET;
        server_addr.sin_port = htons(port);
        
        if (inet_pton(AF_INET, host.c_str(), &server_addr.sin_addr) <= 0) {
            std::cerr << "Invalid address" << std::endl;
            return false;
        }
        
        if (::connect(sock, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
            std::cerr << "Connection failed" << std::endl;
            return false;
        }
        
        return true;
    }
    
    std::string send_command(const std::string& command) {
        if (sock < 0) {
            return "ERROR: Not connected";
        }
        
        if (send(sock, command.c_str(), command.length(), 0) < 0) {
            return "ERROR: Failed to send command";
        }
        
        char buffer[4096];
        memset(buffer, 0, sizeof(buffer));
        int bytes_received = recv(sock, buffer, sizeof(buffer) - 1, 0);
        
        if (bytes_received <= 0) {
            return "ERROR: No response received";
        }
        
        return std::string(buffer);
    }
};

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cout << "Usage: " << argv[0] << " <command> [args...]" << std::endl;
        std::cout << "Commands:" << std::endl;
        std::cout << "  status                    - Get system status" << std::endl;
        std::cout << "  start <script_path>       - Start a workload" << std::endl;
        std::cout << "  stop <pid>                - Stop a process" << std::endl;
        return 1;
    }
    
    TestClient client;
    
    if (!client.connect()) {
        std::cerr << "Failed to connect to Node Agent" << std::endl;
        return 1;
    }
    
    std::string command;
    if (std::string(argv[1]) == "status") {
        command = "STATUS";
    } else if (std::string(argv[1]) == "start") {
        if (argc < 3) {
            std::cerr << "START command requires script path" << std::endl;
            return 1;
        }
        command = "START " + std::string(argv[2]);
    } else if (std::string(argv[1]) == "stop") {
        if (argc < 3) {
            std::cerr << "STOP command requires PID" << std::endl;
            return 1;
        }
        command = "STOP " + std::string(argv[2]);
    } else {
        std::cerr << "Unknown command: " << argv[1] << std::endl;
        return 1;
    }
    
    std::string response = client.send_command(command);
    std::cout << response << std::endl;
    
    return 0;
} 