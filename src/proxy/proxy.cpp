#include <iostream>
#include <string>
#include <vector>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <chrono>
#include <iomanip>

#ifndef _WIN32
#include <sys/wait.h>
#endif

namespace fs = std::filesystem;

// Utility: Get environment variable
std::string get_env(const std::string& name, const std::string& default_value = "") {
    const char* value = std::getenv(name.c_str());
    return value ? std::string(value) : default_value;
}

// Utility: Set environment variable
void set_env(const std::string& name, const std::string& value) {
#ifdef _WIN32
    _putenv_s(name.c_str(), value.c_str());
#else
    setenv(name.c_str(), value.c_str(), 1);
#endif
}

// Utility: Get home directory
std::string get_home_dir() {
#ifdef _WIN32
    const char* home = std::getenv("USERPROFILE");
#else
    const char* home = std::getenv("HOME");
#endif
    return home ? std::string(home) : "";
}

// Utility: Resolve cmake-ctl home directory from env or defaults.
std::string get_cmake_ctl_home() {
    std::string env_home = get_env("CMAKE_CTL_HOME");
    if (env_home.empty()) {
        env_home = get_env("CMAKECTL_HOME");
    }
    if (!env_home.empty()) {
        return env_home;
    }

    // Fallback: use home directory
    std::string home = get_home_dir();
    if (!home.empty()) {
        return home + "/.cmake-ctl";
    }
    return ".cmake-ctl";
}

// Discover source directory from -S flag or build directory
std::string discover_source_dir(const std::vector<std::string>& args) {
    for (size_t i = 0; i < args.size(); ++i) {
        if (args[i] == "-S" && i + 1 < args.size()) {
            return args[i + 1];
        }
    }
    // Default to current directory
    return fs::current_path().string();
}

// Discover build directory from -B flag
std::string discover_build_dir(const std::vector<std::string>& args) {
    for (size_t i = 0; i < args.size(); ++i) {
        if (args[i] == "-B" && i + 1 < args.size()) {
            return args[i + 1];
        }
    }
    // Default to current directory
    return fs::current_path().string();
}

// Emit event to NDJSON file
void emit_event(const std::string& source_dir, const std::string& build_dir, 
                const std::vector<std::string>& args) {
    std::string cmake_ctl_home = get_cmake_ctl_home();
    std::string events_dir = cmake_ctl_home + "/events";
    std::string events_file = events_dir + "/cmake_invocations.ndjson";
    
    // Ensure directory exists
    try {
        fs::create_directories(events_dir);
    } catch (const std::exception&) {
        // Silently fail if unable to create
        return;
    }
    
    // Build args string
    std::string args_str;
    for (size_t i = 0; i < args.size(); ++i) {
        if (i > 0) args_str += " ";
        args_str += args[i];
    }
    
    // Get current timestamp in ISO 8601 format
    auto now = std::chrono::system_clock::now();
    auto time = std::chrono::system_clock::to_time_t(now);
    std::ostringstream oss;
    oss << std::put_time(std::gmtime(&time), "%Y-%m-%dT%H:%M:%SZ");
    std::string timestamp = oss.str();
    
    // Build event JSON
    std::string event = R"({"event":"cmake_invocation","timestamp":")" + timestamp + 
                       R"(","source_dir":")" + source_dir + 
                       R"(","build_dir":")" + build_dir + 
                       R"(","args":")" + args_str + "\"}";
    
    // Append to file
    try {
        std::ofstream file(events_file, std::ios::app);
        if (file.is_open()) {
            file << event << "\n";
            file.close();
        }
    } catch (const std::exception&) {
        // Silently fail if unable to write
    }
}

// Resolve cmake executable path from cmake_ctl managed versions
std::string resolve_cmake_executable() {
    std::string cmake_ctl_home = get_cmake_ctl_home();
    std::string versions_dir = cmake_ctl_home + "/versions";
    std::string config_path = cmake_ctl_home + "/config.json";
    
    // Try to read config.json to find the default version
    std::string default_version;
    try {
        std::ifstream config_file(config_path);
        if (config_file.is_open()) {
            std::stringstream buffer;
            buffer << config_file.rdbuf();
            std::string content = buffer.str();
            
            // Simple JSON parsing for "global_version": "X.Y.Z"
            size_t pos = content.find("\"global_version\"");
            if (pos != std::string::npos) {
                // Find the colon after global_version
                size_t colon_pos = content.find(":", pos);
                if (colon_pos != std::string::npos) {
                    // Find the first quote after the colon
                    size_t start = content.find("\"", colon_pos);
                    if (start != std::string::npos) {
                        // Find the closing quote
                        size_t end = content.find("\"", start + 1);
                        if (end != std::string::npos && end > start) {
                            default_version = content.substr(start + 1, end - start - 1);
                        }
                    }
                }
            }
            config_file.close();
        }
    } catch (...) {}
    
    // If we got a valid version from config, try to use it
    if (!default_version.empty() && default_version[0] != '{' && default_version[0] != '[') {
        // Try Unix-style path first
        std::string cmake_path = versions_dir + "/" + default_version + "/bin/cmake.exe";
        try {
            if (fs::exists(cmake_path)) {
                return fs::canonical(cmake_path).string();
            }
        } catch (...) {}
        
        // Try with forward slashes converted for Windows
        cmake_path = versions_dir + "\\" + default_version + "\\bin\\cmake.exe";
        try {
            if (fs::exists(cmake_path)) {
                return fs::canonical(cmake_path).string();
            }
        } catch (...) {}
    }
    
    // If no version configured or not found, try to find latest installed
    try {
        std::string latest;
        if (fs::exists(versions_dir)) {
            for (const auto& entry : fs::directory_iterator(versions_dir)) {
                if (entry.is_directory()) {
                    std::string dirname = entry.path().filename().string();
                    if (dirname[0] != '.' && dirname[0] != '_') { // Skip temp and hidden directories
                        if (dirname > latest) latest = dirname;
                    }
                }
            }
        }
        
        if (!latest.empty()) {
            std::string cmake_path = versions_dir + "/" + latest + "/bin/cmake.exe";
            try {
                if (fs::exists(cmake_path)) {
                    return fs::canonical(cmake_path).string();
                }
            } catch (...) {}
        }
    } catch (...) {}
    
    // No managed version found - fallback to system cmake
    return "cmake";
}

int main(int argc, char* argv[]) {
    // Resolve cmake executable FIRST (before recursion check)
    std::string cmake_exe = resolve_cmake_executable();
    
    // Check for actual recursion: resolved path equals our own path
    std::string our_path;
    try {
        our_path = fs::canonical(argv[0]).string();
        std::string resolved_canonical = fs::canonical(cmake_exe).string();
        
        // If they're the same, we'd be calling ourselves - that's recursion
        if (our_path == resolved_canonical) {
            std::cerr << "Error: cmake-ctl proxy recursion detected" << std::endl;
            return 1;
        }
    } catch (...) {
        // If we can't resolve paths, just continue
    }
    
    // Set recursion guard for child processes
    set_env("CMAKE_CTL_PROXY_ACTIVE", "1");
    set_env("CMAKECTL_PROXY_ACTIVE", "1");
    
    // Collect arguments (skip program name)
    std::vector<std::string> cmake_args;
    for (int i = 1; i < argc; ++i) {
        cmake_args.push_back(argv[i]);
    }
    
    // Discover source and build directories
    std::string source_dir = discover_source_dir(cmake_args);
    std::string build_dir = discover_build_dir(cmake_args);
    
    // Emit event
    emit_event(source_dir, build_dir, cmake_args);
    
    // If using fallback "cmake", remove proxy bin from PATH to avoid recursion
    if (cmake_exe == "cmake") {
        std::string path = get_env("PATH");
        // Remove cmake-ctl (and legacy cmakectl) bin paths from PATH.
        size_t proxy_bin_pos = path.find("cmake-ctl\\bin");
        if (proxy_bin_pos == std::string::npos) proxy_bin_pos = path.find("cmake-ctl/bin");
        if (proxy_bin_pos == std::string::npos) proxy_bin_pos = path.find("cmakectl\\bin");
        if (proxy_bin_pos == std::string::npos) proxy_bin_pos = path.find("cmakectl/bin");
        if (proxy_bin_pos != std::string::npos) {
            size_t start = proxy_bin_pos;
            // Find the semicolon before
            while (start > 0 && path[start-1] != ';') start--;
            // Find the semicolon after
            size_t end = path.find(';', proxy_bin_pos);
            if (end == std::string::npos) end = path.length();
            
            std::string new_path = path.substr(0, start) + path.substr(end);
            if (!new_path.empty() && new_path[0] == ';') new_path = new_path.substr(1);
            if (!new_path.empty() && new_path[new_path.length()-1] == ';') {
                new_path = new_path.substr(0, new_path.length()-1);
            }
            set_env("PATH", new_path);
        }
    }
    
    // Build command to execute
    std::string command = cmake_exe;
    for (const auto& arg : cmake_args) {
        command += " \"" + arg + "\"";
    }
    
    // Execute cmake with passthrough
    int result = std::system(command.c_str());
    
    // On Windows, system() returns the exit code directly
    // On Unix, we need to use WIFEXITED and WEXITSTATUS macros
#ifdef _WIN32
    return result;
#else
    return WIFEXITED(result) ? WEXITSTATUS(result) : result;
#endif
}
