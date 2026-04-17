#!/bin/bash
# Build script for cmake-ctl proxy on Unix-like systems

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BUILD_DIR="$SCRIPT_DIR/build"
SOURCE_FILE="$SCRIPT_DIR/proxy/src/proxy/proxy.cpp"
OUTPUT_FILE="$SCRIPT_DIR/bin/cmake"

# Create and enter build directory
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

mkdir -p "$SCRIPT_DIR/bin"

build_with_compiler() {
    local compiler="$1"
    echo "Using $compiler compiler..."
    "$compiler" -std=c++17 -O2 "$SOURCE_FILE" -o "$OUTPUT_FILE"
    chmod +x "$OUTPUT_FILE"
    echo "Built cmake proxy to $OUTPUT_FILE"
}

# Configure and build
if command -v cmake >/dev/null 2>&1; then
    if cmake .. && cmake --build . --config Release; then
        # Copy executable to bin directory as cmake
        if [ -f "proxy/cmake-ctl-proxy" ]; then
            cp "proxy/cmake-ctl-proxy" "$OUTPUT_FILE"
            chmod +x "$OUTPUT_FILE"
            echo "Built cmake proxy to $OUTPUT_FILE"
            exit 0
        elif [ -f "proxy/Release/cmake-ctl-proxy" ]; then
            cp "proxy/Release/cmake-ctl-proxy" "$OUTPUT_FILE"
            chmod +x "$OUTPUT_FILE"
            echo "Built cmake proxy to $OUTPUT_FILE"
            exit 0
        elif [ -f "cmake-ctl-proxy" ]; then
            cp "cmake-ctl-proxy" "$OUTPUT_FILE"
            chmod +x "$OUTPUT_FILE"
            echo "Built cmake proxy to $OUTPUT_FILE"
            exit 0
        elif [ -f "Release/cmake-ctl-proxy" ]; then
            cp "Release/cmake-ctl-proxy" "$OUTPUT_FILE"
            chmod +x "$OUTPUT_FILE"
            echo "Built cmake proxy to $OUTPUT_FILE"
            exit 0
        fi
    else
        echo "CMake build failed. Falling back to direct compiler build..."
    fi
else
    echo "CMake not found. Falling back to direct compiler build..."
fi

if command -v c++ >/dev/null 2>&1; then
    build_with_compiler c++
    exit 0
fi

if command -v g++ >/dev/null 2>&1; then
    build_with_compiler g++
    exit 0
fi

if command -v clang++ >/dev/null 2>&1; then
    build_with_compiler clang++
    exit 0
fi

echo "Error: Could not build proxy. Install CMake or a C++ compiler (c++, g++, clang++)."
exit 1
