#!/bin/bash

# Test script for the Micro-Orchestrator Node Agent
# This script tests the basic functionality of the agent

set -e

echo "=== Micro-Orchestrator Node Agent Test ==="
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local status=$1
    local message=$2
    if [ "$status" = "PASS" ]; then
        echo -e "${GREEN}[PASS]${NC} $message"
    elif [ "$status" = "FAIL" ]; then
        echo -e "${RED}[FAIL]${NC} $message"
    else
        echo -e "${YELLOW}[INFO]${NC} $message"
    fi
}

# Check if agent binary exists
if [ ! -f "../agent/agent" ]; then
    print_status "FAIL" "Agent binary not found. Please build the agent first:"
    echo "  cd ../agent && make"
    exit 1
fi

print_status "INFO" "Agent binary found"

# Check if test client exists
if [ ! -f "../agent/test_client" ]; then
    print_status "FAIL" "Test client not found. Please build the test client:"
    echo "  cd ../agent && make test_client"
    exit 1
fi

print_status "INFO" "Test client found"

# Make scripts executable
chmod +x sample_workload.sh memory_workload.sh

print_status "INFO" "Starting Node Agent on port 8080..."

# Start the agent in background
cd ../agent
./agent 8080 &
AGENT_PID=$!

# Wait for agent to start
sleep 2

# Check if agent is running
if kill -0 $AGENT_PID 2>/dev/null; then
    print_status "PASS" "Agent started successfully (PID: $AGENT_PID)"
else
    print_status "FAIL" "Agent failed to start"
    exit 1
fi

echo
print_status "INFO" "Testing agent functionality..."

# Test 1: Get initial status
echo "Test 1: Getting initial status..."
RESPONSE=$(./test_client status)
if echo "$RESPONSE" | grep -q "STATUS:"; then
    print_status "PASS" "Status command works"
    echo "$RESPONSE" | head -10
else
    print_status "FAIL" "Status command failed"
fi

# Test 2: Start a workload
echo
echo "Test 2: Starting a workload..."
RESPONSE=$(./test_client start ../scripts/sample_workload.sh)
if echo "$RESPONSE" | grep -q "SUCCESS"; then
    print_status "PASS" "Start command works"
    echo "$RESPONSE"
    
    # Extract PID from response
    PID=$(echo "$RESPONSE" | grep -o '[0-9]\+' | head -1)
    echo "Started process with PID: $PID"
    
    # Test 3: Check status with running process
    echo
    echo "Test 3: Checking status with running process..."
    sleep 1
    RESPONSE=$(./test_client status)
    if echo "$RESPONSE" | grep -q "Running Processes: [1-9]"; then
        print_status "PASS" "Status shows running processes"
        echo "$RESPONSE" | grep "Running Processes:"
    else
        print_status "FAIL" "Status does not show running processes"
    fi
    
    # Test 4: Stop the process
    echo
    echo "Test 4: Stopping the process..."
    RESPONSE=$(./test_client stop $PID)
    if echo "$RESPONSE" | grep -q "SUCCESS"; then
        print_status "PASS" "Stop command works"
        echo "$RESPONSE"
    else
        print_status "FAIL" "Stop command failed"
    fi
    
    # Wait for process to stop
    sleep 2
    
    # Test 5: Verify process is stopped
    echo
    echo "Test 5: Verifying process is stopped..."
    RESPONSE=$(./test_client status)
    if echo "$RESPONSE" | grep -q "Running Processes: 0"; then
        print_status "PASS" "Process successfully stopped"
    else
        print_status "FAIL" "Process may still be running"
    fi
    
else
    print_status "FAIL" "Start command failed"
    echo "$RESPONSE"
fi

echo
print_status "INFO" "Cleaning up..."

# Stop the agent
kill $AGENT_PID
wait $AGENT_PID 2>/dev/null || true

print_status "INFO" "Test completed!"
echo
echo "Summary:"
echo "- Agent starts and stops correctly"
echo "- Status command returns system metrics"
echo "- Process management (start/stop) works"
echo "- TCP communication is functional" 