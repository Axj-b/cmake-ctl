@echo off
REM Build script for cmake-ctl proxy on Windows

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set BUILD_DIR=%SCRIPT_DIR%build
set SOURCE_FILE=%SCRIPT_DIR%proxy\src\proxy\proxy.cpp
set OUTPUT_FILE=%SCRIPT_DIR%bin\cmake.exe
set TOOL_LIST=ctest.exe cpack.exe ccmake.exe cmake-gui.exe cmcldeps.exe
if "%CMAKE_CTL_PROXY_VERSION%"=="" (
    set PROXY_VERSION=0.1.0
) else (
    set PROXY_VERSION=%CMAKE_CTL_PROXY_VERSION%
)

if not exist "%SCRIPT_DIR%bin" mkdir "%SCRIPT_DIR%bin"

where cmake >nul 2>nul
if errorlevel 1 (
    echo CMake not found. Falling back to direct compiler build...
    goto direct_build
)

REM Create build directory
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"
cd /d "%BUILD_DIR%"

REM Configure with CMake
cmake -DCMAKE_CTL_PROXY_VERSION="%PROXY_VERSION%" ..
if !errorlevel! neq 0 (
    echo CMake configuration failed. Falling back to direct compiler build...
    cd /d "%SCRIPT_DIR%"
    goto direct_build
)

REM Build
cmake --build . --config Release
if !errorlevel! neq 0 (
    echo CMake build failed. Falling back to direct compiler build...
    cd /d "%SCRIPT_DIR%"
    goto direct_build
)

REM Copy executable to bin directory as cmake.exe
if exist "proxy\Release\cmake-ctl-proxy.exe" (
    copy /Y "proxy\Release\cmake-ctl-proxy.exe" "%OUTPUT_FILE%"
    for %%T in (%TOOL_LIST%) do copy /Y "%OUTPUT_FILE%" "%SCRIPT_DIR%bin\%%T" >nul
    echo Build complete: %OUTPUT_FILE%
    exit /b 0
) else if exist "Release\cmake-ctl-proxy.exe" (
    copy /Y "Release\cmake-ctl-proxy.exe" "%OUTPUT_FILE%"
    for %%T in (%TOOL_LIST%) do copy /Y "%OUTPUT_FILE%" "%SCRIPT_DIR%bin\%%T" >nul
    echo Build complete: %OUTPUT_FILE%
    exit /b 0
) else if exist "cmake-ctl-proxy.exe" (
    copy /Y "cmake-ctl-proxy.exe" "%OUTPUT_FILE%"
    for %%T in (%TOOL_LIST%) do copy /Y "%OUTPUT_FILE%" "%SCRIPT_DIR%bin\%%T" >nul
    echo Build complete: %OUTPUT_FILE%
    exit /b 0
) else (
    echo CMake finished but output executable was not found. Falling back to direct compiler build...
    cd /d "%SCRIPT_DIR%"
    goto direct_build
)

:direct_build
where cl >nul 2>nul
if not errorlevel 1 (
    echo Using MSVC cl compiler...
    cl /nologo /EHsc /std:c++17 /DCMAKE_CTL_PROXY_VERSION="\"%PROXY_VERSION%\"" "%SOURCE_FILE%" /Fe:"%OUTPUT_FILE%" shell32.lib
    if !errorlevel! equ 0 if exist "%OUTPUT_FILE%" (
        for %%T in (%TOOL_LIST%) do copy /Y "%OUTPUT_FILE%" "%SCRIPT_DIR%bin\%%T" >nul
        echo Build complete: %OUTPUT_FILE%
        exit /b 0
    )
)

where clang++ >nul 2>nul
if not errorlevel 1 (
    echo Using clang++ compiler...
    clang++ -std=c++17 -O2 -DCMAKE_CTL_PROXY_VERSION=\"%PROXY_VERSION%\" "%SOURCE_FILE%" -o "%OUTPUT_FILE%" -lshell32
    if !errorlevel! equ 0 if exist "%OUTPUT_FILE%" (
        for %%T in (%TOOL_LIST%) do copy /Y "%OUTPUT_FILE%" "%SCRIPT_DIR%bin\%%T" >nul
        echo Build complete: %OUTPUT_FILE%
        exit /b 0
    )
)

where g++ >nul 2>nul
if not errorlevel 1 (
    echo Using g++ compiler...
    g++ -std=c++17 -O2 -DCMAKE_CTL_PROXY_VERSION=\"%PROXY_VERSION%\" "%SOURCE_FILE%" -o "%OUTPUT_FILE%" -lshell32
    if !errorlevel! equ 0 if exist "%OUTPUT_FILE%" (
        for %%T in (%TOOL_LIST%) do copy /Y "%OUTPUT_FILE%" "%SCRIPT_DIR%bin\%%T" >nul
        echo Build complete: %OUTPUT_FILE%
        exit /b 0
    )
)

echo Error: Could not build proxy. Install CMake or use a shell with cl or g++ available.
exit /b 1
