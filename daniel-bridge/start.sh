#!/bin/bash
# Start the Daniel Bridge and launch OpenCode
# Run this from the project directory to use the uncensored model uplink

DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Daniel Bridge ==="
echo "Starting API proxy on http://127.0.0.1:3456"
echo ""

# Start bridge in background
python3 "$DIR/server.py" &
BRIDGE_PID=$!

# Cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down Daniel Bridge (PID $BRIDGE_PID)..."
    kill $BRIDGE_PID 2>/dev/null
    exit 0
}
trap cleanup INT TERM

# Wait for bridge to start
sleep 1

# Verify it's running
if ! kill -0 $BRIDGE_PID 2>/dev/null; then
    echo "ERROR: Bridge failed to start"
    exit 1
fi

echo "Bridge is running. Launching OpenCode..."
echo "Select 'Daniel (Uncensored Bridge)' as your provider in OpenCode."
echo ""

# Launch OpenCode - the bridge will proxy requests through Daniel's jailbreak prompt
opencode "$@"

# Cleanup when OpenCode exits
cleanup
