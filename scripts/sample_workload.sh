#!/bin/bash

# Sample workload script for testing the Node Agent
# This script simulates a CPU-intensive task

echo "Starting sample workload: $(date)"
echo "PID: $$"
echo "Hostname: $(hostname)"

# Simulate some work
counter=0
while true; do
    # Do some CPU work
    for i in {1..1000}; do
        echo "Working iteration $counter, step $i" > /dev/null
    done
    
    # Sleep for a bit to prevent 100% CPU usage
    sleep 1
    
    counter=$((counter + 1))
    
    # Log progress every 10 iterations
    if [ $((counter % 10)) -eq 0 ]; then
        echo "Workload progress: $counter iterations completed"
    fi
done 