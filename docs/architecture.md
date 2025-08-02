# Micro-Orchestrator Architecture

## Overview

The Micro-Orchestrator is a high-performance distributed process orchestration system designed for managing workloads across multiple Linux nodes. The system consists of two primary components:

1. **Python Scheduler** (Phase 2): Central decision-making component
2. **C++ Node Agents** (Phase 1): High-performance agents for process management

## System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Python        │    │   C++ Node      │    │   C++ Node      │
│   Scheduler     │◄──►│   Agent #1      │    │   Agent #2      │
│                 │    │                 │    │                 │
│ • Workload      │    │ • Process Mgmt  │    │ • Process Mgmt  │
│   Distribution  │    │ • Metrics       │    │ • Metrics       │
│ • Load          │    │ • TCP Server    │    │ • TCP Server    │
│   Balancing     │    │ • Local State   │    │ • Local State   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Phase 1: C++ Node Agent

### Core Features

#### 1. Process Management
- **Fork/Exec Model**: Uses `fork()` and `execvp()` for process creation
- **PID Tracking**: Maintains a thread-safe map of running processes
- **Graceful Shutdown**: Sends SIGTERM first, then SIGKILL if needed
- **Zombie Cleanup**: Automatic cleanup of terminated processes

#### 2. System Metrics Collection
- **CPU Usage**: Parses `/proc/stat` for real-time CPU utilization
- **Memory Usage**: Reads `/proc/meminfo` for memory statistics
- **Process Count**: Tracks number of managed processes
- **Real-time Updates**: Continuous monitoring with configurable intervals

#### 3. Multi-threaded TCP Server
- **Concurrent Connections**: Handles multiple client connections simultaneously
- **Thread Pool**: Pre-allocated worker threads for background tasks
- **Command Protocol**: Simple text-based protocol for agent communication
- **Graceful Shutdown**: Proper cleanup on termination signals

### API Commands

The Node Agent accepts the following commands via TCP:

| Command | Format | Description |
|---------|--------|-------------|
| `START` | `START <script_path>` | Start a new workload process |
| `STOP` | `STOP <pid>` | Stop a running process by PID |
| `STATUS` | `STATUS` | Get system metrics and process list |

### Response Format

```
STATUS:
CPU Usage: 25.50%
Memory Usage: 45.20%
Total Memory: 8192 KB
Available Memory: 4489 KB
Running Processes: 3

Processes:
PID: 1234 | Command: /path/to/script.sh | Started: 2024-01-15 10:30:45 | Status: RUNNING
PID: 1235 | Command: /path/to/other.sh | Started: 2024-01-15 10:31:00 | Status: RUNNING
```

### Internal Data Structures

#### SystemMetrics
```cpp
struct SystemMetrics {
    double cpu_usage;        // CPU usage percentage
    double memory_usage;     // Memory usage percentage
    long total_memory;       // Total system memory (KB)
    long available_memory;   // Available memory (KB)
    int running_processes;   // Number of managed processes
};
```

#### ProcessInfo
```cpp
struct ProcessInfo {
    pid_t pid;              // Process ID
    std::string command;    // Command/script path
    std::string start_time; // Process start timestamp
    std::string status;     // Current status (RUNNING, STOPPED, etc.)
};
```

### Thread Safety

- **Process Map**: Protected by `std::mutex` for thread-safe access
- **Metrics Collection**: Atomic operations for CPU time tracking
- **TCP Server**: Each client connection handled in separate thread
- **Worker Threads**: Background cleanup and monitoring tasks

### Performance Characteristics

- **Low Latency**: Direct system calls for process management
- **High Throughput**: Multi-threaded design for concurrent operations
- **Memory Efficient**: Minimal overhead for process tracking
- **Real-time Metrics**: Direct `/proc` filesystem access

## File Structure

```
micro-orchestrator/
├── agent/
│   ├── node_agent.h          # Main header file
│   ├── node_agent.cpp        # Core implementation
│   ├── main.cpp              # Entry point
│   ├── test_client.cpp       # Test client
│   └── Makefile              # Build configuration
├── scripts/
│   ├── sample_workload.sh    # CPU-intensive test workload
│   └── memory_workload.sh    # Memory-intensive test workload
├── docs/
│   └── architecture.md       # This documentation
└── README.md                 # Project overview
```

## Building and Testing

### Prerequisites
- GCC 7+ with C++17 support
- Linux environment (for `/proc` filesystem and `fork()`)
- pthread library

### Build Commands
```bash
cd agent
make                    # Build agent and test client
make agent             # Build only the agent
make test_client       # Build only the test client
make clean             # Clean build artifacts
```

### Testing
```bash
# Terminal 1: Start the agent
./agent 8080

# Terminal 2: Test commands
./test_client status
./test_client start ../scripts/sample_workload.sh
./test_client stop <pid>
```

## Future Enhancements (Phase 2)

1. **Python Scheduler**: Central orchestration component
2. **Load Balancing**: Intelligent workload distribution
3. **Fault Tolerance**: Automatic failover and recovery
4. **Monitoring Dashboard**: Web-based monitoring interface
5. **Configuration Management**: Dynamic agent configuration
6. **Security**: Authentication and encryption for agent communication 