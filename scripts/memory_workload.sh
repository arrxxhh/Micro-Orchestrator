#!/bin/bash

# Memory-intensive workload script for testing the Node Agent
# This script allocates memory to test memory monitoring

echo "Starting memory workload: $(date)"
echo "PID: $$"

# Allocate memory in chunks
chunk_size=10M
max_chunks=50
chunks=0

echo "Allocating memory in $chunk_size chunks..."

while [ $chunks -lt $max_chunks ]; do
    # Allocate memory using dd
    dd if=/dev/zero of=/tmp/memory_chunk_$chunks bs=$chunk_size count=1 2>/dev/null
    
    chunks=$((chunks + 1))
    echo "Allocated chunk $chunks of $max_chunks"
    
    # Sleep between allocations
    sleep 2
done

echo "Memory allocation complete. Holding memory for 30 seconds..."
sleep 30

echo "Cleaning up allocated memory..."
rm -f /tmp/memory_chunk_*

echo "Memory workload completed: $(date)" 