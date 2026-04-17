@echo off
REM Build script for cmakectl proxy on Windows

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
if exist "Release\cmakectl-proxy.exe" (
    copy "Release\cmakectl-proxy.exe" "%SCRIPT_DIR%bin\cmakectl-proxy.exe"
    echo Build complete: %SCRIPT_DIR%bin\cmakectl-proxy.exe
) else if exist "cmakectl-proxy.exe" (
    copy "cmakectl-proxy.exe" "%SCRIPT_DIR%bin\cmakectl-proxy.exe"
    echo Build complete: %SCRIPT_DIR%bin\cmakectl-proxy.exe
) else (
    echo Error: cmakectl-proxy.exe not found after build
    exit /b 1
)
