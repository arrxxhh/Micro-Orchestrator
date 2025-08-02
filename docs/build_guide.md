# Build and Test Guide

## Prerequisites

### System Requirements
- **Operating System**: Linux (required for `/proc` filesystem and `fork()`)
- **Compiler**: GCC 7+ with C++17 support
- **Libraries**: pthread (usually included with GCC)
- **Permissions**: Ability to create and execute processes

### Development Environment
```bash
# Install build tools (Ubuntu/Debian)
sudo apt update
sudo apt install build-essential g++ make

# Install build tools (CentOS/RHEL)
sudo yum groupinstall "Development Tools"
```

## Building the Node Agent

### Step 1: Navigate to the Agent Directory
```bash
cd agent
```

### Step 2: Build the Agent
```bash
# Build both agent and test client
make

# Or build individually
make agent        # Build only the Node Agent
make test_client  # Build only the test client
```

### Step 3: Verify Build
```bash
# Check that binaries were created
ls -la agent test_client

# Check binary information
file agent test_client
```

## Running the Node Agent

### Basic Usage
```bash
# Start agent on default port (8080)
./agent

# Start agent on custom port
./agent 9090

# Start agent in background
./agent 8080 &
```

### Command Line Options
- **Port**: Specify port number (1-65535)
- **Default**: 8080 if no port specified
- **Signal Handling**: Ctrl+C for graceful shutdown

### Example Session
```bash
$ ./agent 8080
Starting Micro-Orchestrator Node Agent...
Port: 8080
Node Agent started on port 8080
Node Agent is running. Press Ctrl+C to stop.
```

## Testing the Node Agent

### Automated Test Script
```bash
# Run the comprehensive test script
cd scripts
chmod +x test_agent.sh
./test_agent.sh
```

### Manual Testing

#### 1. Start the Agent
```bash
cd agent
./agent 8080 &
AGENT_PID=$!
```

#### 2. Test Status Command
```bash
./test_client status
```

Expected output:
```
STATUS:
CPU Usage: 15.23%
Memory Usage: 45.67%
Total Memory: 8192 KB
Available Memory: 4448 KB
Running Processes: 0

Processes:
```

#### 3. Test Process Management
```bash
# Start a workload
./test_client start ../scripts/sample_workload.sh

# Check status with running process
./test_client status

# Stop the process (replace PID with actual PID)
./test_client stop 1234
```

#### 4. Test Memory Workload
```bash
# Start memory-intensive workload
./test_client start ../scripts/memory_workload.sh

# Monitor memory usage
./test_client status
```

### Network Testing
```bash
# Test from another machine (replace IP)
./test_client status
```

## Troubleshooting

### Common Issues

#### 1. Build Failures
```bash
# Check compiler version
g++ --version

# Check C++17 support
echo '#include <optional>' | g++ -std=c++17 -x c++ - -o /dev/null

# Clean and rebuild
make clean
make
```

#### 2. Permission Issues
```bash
# Make scripts executable
chmod +x ../scripts/*.sh

# Check if agent can create processes
./agent 8080
```

#### 3. Port Already in Use
```bash
# Check what's using the port
netstat -tulpn | grep :8080

# Use a different port
./agent 8081
```

#### 4. Process Management Issues
```bash
# Check if fork() works
echo 'int main() { return fork() >= 0 ? 0 : 1; }' | g++ -x c++ - -o test_fork && ./test_fork && echo "fork() works" || echo "fork() failed"

# Check /proc filesystem
ls /proc/stat /proc/meminfo
```

### Debug Mode
```bash
# Build with debug symbols
make clean
CXXFLAGS="-std=c++17 -Wall -Wextra -g -O0 -pthread" make

# Run with gdb
gdb ./agent
```

## Performance Testing

### Load Testing
```bash
# Start multiple workloads
for i in {1..5}; do
    ./test_client start ../scripts/sample_workload.sh &
done

# Check system status
./test_client status

# Stop all processes
pkill -f sample_workload.sh
```

### Memory Testing
```bash
# Start memory-intensive workload
./test_client start ../scripts/memory_workload.sh

# Monitor memory usage
watch -n 1 './test_client status | grep Memory'
```

### Concurrent Connection Testing
```bash
# Test multiple simultaneous connections
for i in {1..10}; do
    ./test_client status &
done
wait
```

## Integration Testing

### Test with Real Workloads
```bash
# Create a custom workload script
cat > ../scripts/custom_workload.sh << 'EOF'
#!/bin/bash
echo "Custom workload started: $(date)"
sleep 30
echo "Custom workload completed: $(date)"
EOF

chmod +x ../scripts/custom_workload.sh

# Test the custom workload
./test_client start ../scripts/custom_workload.sh
```

### Stress Testing
```bash
# Create stress test script
cat > stress_test.sh << 'EOF'
#!/bin/bash
for i in {1..20}; do
    ./test_client start ../scripts/sample_workload.sh &
    sleep 0.1
done

sleep 5

./test_client status

# Clean up
pkill -f sample_workload.sh
EOF

chmod +x stress_test.sh
./stress_test.sh
```

## Monitoring and Logging

### System Metrics
The Node Agent provides real-time system metrics:
- CPU usage percentage
- Memory usage percentage
- Total and available memory
- Number of running processes

### Process Tracking
- Process ID (PID)
- Command/script path
- Start timestamp
- Current status

### Network Communication
- TCP socket on specified port
- Text-based command protocol
- Concurrent connection handling

## Security Considerations

### Current Limitations
- No authentication
- No encryption
- No access control
- Plain text communication

### Recommendations for Production
- Implement TLS/SSL encryption
- Add authentication mechanism
- Use firewall rules
- Implement rate limiting
- Add logging and monitoring

## Next Steps (Phase 2)

1. **Python Scheduler Development**
2. **Load Balancing Implementation**
3. **Fault Tolerance Features**
4. **Security Enhancements**
5. **Monitoring Dashboard**
6. **Configuration Management** 