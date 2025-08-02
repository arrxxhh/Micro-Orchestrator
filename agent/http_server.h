#ifndef HTTP_SERVER_H
#define HTTP_SERVER_H

#include "node_agent.h"
#include <string>
#include <map>
#include <functional>

class HttpServer {
private:
    NodeAgent& agent;
    int server_socket;
    int port;
    std::atomic<bool> running;
    std::map<std::string, std::function<std::string(const std::string&)>> routes;

public:
    HttpServer(NodeAgent& agent, int port = 8080);
    ~HttpServer();
    
    bool start_server();
    void stop_server();
    void run_server();
    
    // HTTP response helpers
    std::string create_json_response(const std::string& data, int status_code = 200);
    std::string create_error_response(const std::string& error, int status_code = 400);
    
    // Route handlers
    std::string handle_status_request();
    std::string handle_start_request(const std::string& body);
    std::string handle_stop_request(const std::string& body);
    
    // HTTP parsing
    std::map<std::string, std::string> parse_headers(const std::string& request);
    std::string parse_json_field(const std::string& json, const std::string& field);
    
    // Client handling
    void handle_client(int client_socket);
    std::string read_request(int client_socket);
    void send_response(int client_socket, const std::string& response);
};

#endif // HTTP_SERVER_H 