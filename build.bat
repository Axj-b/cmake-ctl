@echo off
REM Build script for cmake-ctl proxy on Windows

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set BUILD_DIR=%SCRIPT_DIR%build

REM Create build directory
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"
cd /d "%BUILD_DIR%"

REM Configure with CMake
cmake ..
if !errorlevel! neq 0 (
    echo Error: CMake configuration failed
    exit /b 1
)

REM Build
cmake --build . --config Release
if !errorlevel! neq 0 (
    echo Error: Build failed
    exit /b 1
)

REM Copy executable to bin directory
if exist "Release\cmake-ctl-proxy.exe" (
    copy "Release\cmake-ctl-proxy.exe" "%SCRIPT_DIR%bin\cmake-ctl-proxy.exe"
    echo Build complete: %SCRIPT_DIR%bin\cmake-ctl-proxy.exe
) else if exist "cmake-ctl-proxy.exe" (
    copy "cmake-ctl-proxy.exe" "%SCRIPT_DIR%bin\cmake-ctl-proxy.exe"
    echo Build complete: %SCRIPT_DIR%bin\cmake-ctl-proxy.exe
) else (
    echo Error: cmake-ctl-proxy.exe not found after build
    exit /b 1
)
