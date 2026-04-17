#!/bin/bash
# Build script for cmakectl proxy on Unix-like systems

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
if [ -f "cmakectl-proxy" ]; then
    cp cmakectl-proxy "$SCRIPT_DIR/bin/cmakectl-proxy"
    chmod +x "$SCRIPT_DIR/bin/cmakectl-proxy"
    echo "✓ Built cmakectl-proxy to $SCRIPT_DIR/bin/cmakectl-proxy"
elif [ -f "Release/cmakectl-proxy" ]; then
    cp "Release/cmakectl-proxy" "$SCRIPT_DIR/bin/cmakectl-proxy"
    chmod +x "$SCRIPT_DIR/bin/cmakectl-proxy"
    echo "✓ Built cmakectl-proxy to $SCRIPT_DIR/bin/cmakectl-proxy"
fi
