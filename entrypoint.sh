#!/bin/bash
# Create /data directory structure
mkdir -p /data/{config,log}

# Start the main process and save its PID
# Use exec to replace the shell script process with the main process
exec gunicorn main:APP --bind 0.0.0.0:80 &

pid=$!

# Trap the SIGTERM signal and forward it to the main process
trap 'kill -SIGTERM $pid; wait $pid' SIGTERM

# Wait for the main process to complete
wait $pid
