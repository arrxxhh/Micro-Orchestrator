#include "node_agent.h"
#include "http_server.h"
#include <iostream>
#include <signal.h>

std::atomic<bool> shutdown_requested(false);

void signal_handler(int signal) {
    if (signal == SIGINT || signal == SIGTERM) {
        std::cout << "\nReceived shutdown signal. Stopping Node Agent..." << std::endl;
        shutdown_requested = true;
    }
}

int main(int argc, char* argv[]) {
    int port = 8080;
    
    // Parse command line arguments
    if (argc > 1) {
        try {
            port = std::stoi(argv[1]);
            if (port <= 0 || port > 65535) {
                std::cerr << "Invalid port number. Must be between 1 and 65535." << std::endl;
                return 1;
            }
        } catch (const std::exception& e) {
            std::cerr << "Invalid port number: " << argv[1] << std::endl;
            return 1;
        }
    }
    
    // Set up signal handlers
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    std::cout << "Starting Micro-Orchestrator Node Agent..." << std::endl;
    std::cout << "Port: " << port << std::endl;
    
    // Create the Node Agent
    NodeAgent agent(port);
    
    // Create and start the HTTP Server
    HttpServer http_server(agent, port);
    
    if (!http_server.start_server()) {
        std::cerr << "Failed to start HTTP server" << std::endl;
        return 1;
    }
    
    std::cout << "Node Agent is running. Press Ctrl+C to stop." << std::endl;
    
    // Run the HTTP server until shutdown is requested
    while (!shutdown_requested) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    
    std::cout << "Shutting down Node Agent..." << std::endl;
    http_server.stop_server();
    
    std::cout << "Node Agent stopped." << std::endl;
    return 0;
} 