#!/bin/bash
# Build script for cmake-ctl proxy on Unix-like systems

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BUILD_DIR="$SCRIPT_DIR/build"

# Create and enter build directory
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

# Configure and build
cmake ..
cmake --build . --config Release

# Copy executable to bin directory
if [ -f "cmake-ctl-proxy" ]; then
    cp cmake-ctl-proxy "$SCRIPT_DIR/bin/cmake-ctl-proxy"
    chmod +x "$SCRIPT_DIR/bin/cmake-ctl-proxy"
    echo "✓ Built cmake-ctl-proxy to $SCRIPT_DIR/bin/cmake-ctl-proxy"
elif [ -f "Release/cmake-ctl-proxy" ]; then
    cp "Release/cmake-ctl-proxy" "$SCRIPT_DIR/bin/cmake-ctl-proxy"
    chmod +x "$SCRIPT_DIR/bin/cmake-ctl-proxy"
    echo "✓ Built cmake-ctl-proxy to $SCRIPT_DIR/bin/cmake-ctl-proxy"
fi
