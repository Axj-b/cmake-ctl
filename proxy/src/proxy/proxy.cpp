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
#include <algorithm>
#include <cctype>

#define CMAKE_CTL_PROXY_VERSION "0.1.0"

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
            try {
                return fs::absolute(args[i + 1]).lexically_normal().string();
            } catch (...) {
                return args[i + 1];
            }
        }
    }
    // Default to current directory
    return fs::current_path().string();
}

// Discover build directory from -B flag
std::string discover_build_dir(const std::vector<std::string>& args) {
    for (size_t i = 0; i < args.size(); ++i) {
        if (args[i] == "-B" && i + 1 < args.size()) {
            try {
                return fs::absolute(args[i + 1]).lexically_normal().string();
            } catch (...) {
                return args[i + 1];
            }
        }
    }
    // Default to current directory
    return fs::current_path().string();
}

std::string json_escape(const std::string& in) {
    std::string out;
    out.reserve(in.size() + 16);
    for (char c : in) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default: out += c; break;
        }
    }
    return out;
}

std::string json_array_of_strings(const std::vector<std::string>& values) {
    std::string out = "[";
    for (size_t i = 0; i < values.size(); ++i) {
        if (i > 0) out += ",";
        out += "\"" + json_escape(values[i]) + "\"";
    }
    out += "]";
    return out;
}

std::vector<int> parse_version_parts(const std::string& version) {
    std::vector<int> parts;
    std::stringstream ss(version);
    std::string token;
    while (std::getline(ss, token, '.')) {
        try {
            size_t consumed = 0;
            int value = std::stoi(token, &consumed);
            if (consumed != token.size()) {
                value = 0;
            }
            parts.push_back(value);
        } catch (...) {
            parts.push_back(0);
        }
    }
    return parts;
}

bool version_greater_than(const std::string& lhs, const std::string& rhs) {
    std::vector<int> a = parse_version_parts(lhs);
    std::vector<int> b = parse_version_parts(rhs);
    size_t n = std::max(a.size(), b.size());
    a.resize(n, 0);
    b.resize(n, 0);
    for (size_t i = 0; i < n; ++i) {
        if (a[i] != b[i]) {
            return a[i] > b[i];
        }
    }
    return false;
}

std::string to_lower(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return value;
}

std::string tool_from_argv0(const char* argv0) {
    if (argv0 == nullptr || std::strlen(argv0) == 0) {
        return "cmake";
    }
    std::string stem = fs::path(argv0).stem().string();
    if (stem.empty()) {
        return "cmake";
    }
    std::string tool = to_lower(stem);
    if (
        tool == "cmake" ||
        tool == "ctest" ||
        tool == "cpack" ||
        tool == "ccmake" ||
        tool == "cmake-gui" ||
        tool == "cmcldeps"
    ) {
        return tool;
    }
    return "cmake";
}

std::string find_tool_in_version(const std::string& versions_dir, const std::string& version, const std::string& tool_name) {
    fs::path base = fs::path(versions_dir) / version / "bin";
    std::vector<std::string> names;
#ifdef _WIN32
    names = {tool_name + ".exe", tool_name};
#else
    names = {tool_name};
#endif
    for (const auto& name : names) {
        fs::path candidate = base / name;
        try {
            if (fs::exists(candidate)) {
                return fs::canonical(candidate).string();
            }
        } catch (...) {
        }
    }
    return "";
}

// Emit event to NDJSON file
void emit_event(const std::string& source_dir, const std::string& build_dir, 
                const std::vector<std::string>& args) {
    std::string cmake_ctl_home = get_cmake_ctl_home();
    std::string events_file = cmake_ctl_home + "/events.log";
    
    // Ensure parent directory exists
    try {
        fs::create_directories(cmake_ctl_home);
    } catch (const std::exception&) {
        // Silently fail if unable to create
        return;
    }
    
    // Get current timestamp in ISO 8601 format
    auto now = std::chrono::system_clock::now();
    auto time = std::chrono::system_clock::to_time_t(now);
    std::ostringstream oss;
    oss << std::put_time(std::gmtime(&time), "%Y-%m-%dT%H:%M:%SZ");
    std::string timestamp = oss.str();
    auto nonce = std::chrono::duration_cast<std::chrono::microseconds>(
        now.time_since_epoch()).count();
    std::string event_id = "cpp-" + std::to_string(nonce);
    
    std::string cwd = fs::current_path().string();

    // Build canonical event JSON expected by Python processor.
    std::string event =
        "{\"schema_version\":1,"
        "\"event_id\":\"" + json_escape(event_id) + "\"," 
        "\"event_type\":\"cmake_invocation\"," 
        "\"payload\":{" 
            "\"project_path\":\"" + json_escape(source_dir) + "\"," 
            "\"source_dir\":\"" + json_escape(source_dir) + "\"," 
            "\"build_dir\":\"" + json_escape(build_dir) + "\"," 
            "\"cwd\":\"" + json_escape(cwd) + "\"," 
            "\"argv\":" + json_array_of_strings(args) + "," 
            "\"resolved_version\":\"\"," 
            "\"source\":\"cpp-proxy\"," 
            "\"timestamp\":\"" + json_escape(timestamp) + "\"" 
        "}}";
    
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

// Resolve proxied executable path from cmake-ctl managed versions
std::string resolve_tool_executable(const std::string& tool_name) {
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
    
    // If we got a valid version from config, try to use it.
    if (!default_version.empty() && default_version[0] != '{' && default_version[0] != '[') {
        std::string managed = find_tool_in_version(versions_dir, default_version, tool_name);
        if (!managed.empty()) {
            return managed;
        }
    }
    
    // If no version configured or not found, try to find latest installed
    try {
        std::string latest;
        if (fs::exists(versions_dir)) {
            for (const auto& entry : fs::directory_iterator(versions_dir)) {
                if (entry.is_directory()) {
                    std::string dirname = entry.path().filename().string();
                    if (dirname[0] != '.' && dirname[0] != '_') { // Skip temp and hidden directories
                        if (latest.empty() || version_greater_than(dirname, latest)) latest = dirname;
                    }
                }
            }
        }
        
        if (!latest.empty()) {
            std::string managed = find_tool_in_version(versions_dir, latest, tool_name);
            if (!managed.empty()) {
                return managed;
            }
        }
    } catch (...) {}
    
    // No managed version found - fallback to system tool.
    return tool_name;
}

std::string read_cmake_ctl_version(const std::string& config_path) {
    try {
        std::ifstream config_file(config_path);
        if (!config_file.is_open()) {
            return CMAKE_CTL_PROXY_VERSION;
        }
        std::stringstream buffer;
        buffer << config_file.rdbuf();
        std::string content = buffer.str();
        size_t pos = content.find("\"cli_version\"");
        if (pos != std::string::npos) {
            size_t colon_pos = content.find(":", pos);
            if (colon_pos != std::string::npos) {
                size_t start = content.find("\"", colon_pos);
                if (start != std::string::npos) {
                    size_t end = content.find("\"", start + 1);
                    if (end != std::string::npos && end > start) {
                        std::string value = content.substr(start + 1, end - start - 1);
                        if (!value.empty()) {
                            return value;
                        }
                    }
                }
            }
        }
    } catch (...) {
    }
    return CMAKE_CTL_PROXY_VERSION;
}

int main(int argc, char* argv[]) {
    std::string tool_name = tool_from_argv0(argc > 0 ? argv[0] : nullptr);
    std::string cmake_ctl_home = get_cmake_ctl_home();
    std::string config_path = cmake_ctl_home + "/config.json";

    // Resolve managed executable FIRST (before recursion check)
    std::string tool_exe = resolve_tool_executable(tool_name);
    
    // Check for actual recursion: resolved path equals our own path
    std::string our_path;
    try {
        our_path = fs::canonical(argv[0]).string();
        std::string resolved_canonical = fs::canonical(tool_exe).string();
        
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
    
    // Collect arguments (skip program name)
    std::vector<std::string> cmake_args;
    for (int i = 1; i < argc; ++i) {
        cmake_args.push_back(argv[i]);
    }
    
    // Discover source and build directories
    std::string source_dir = discover_source_dir(cmake_args);
    std::string build_dir = discover_build_dir(cmake_args);
    
    if (tool_name == "cmake") {
        emit_event(source_dir, build_dir, cmake_args);
    }

    std::string resolved_version = "unknown";
    fs::path tool_path(tool_exe);
    if (tool_path.is_absolute()) {
        fs::path parent = tool_path.parent_path();
        if (parent.filename() == "bin") {
            fs::path version_dir = parent.parent_path();
            std::string version_name = version_dir.filename().string();
            if (!version_name.empty()) {
                resolved_version = version_name;
            }
        }
    }

    std::cerr
        << "[cmake-ctl "
        << read_cmake_ctl_version(config_path)
        << "] "
        << tool_name
        << " -> CMake "
        << resolved_version
        << std::endl;
    
    // If using fallback system tool, remove proxy bin from PATH to avoid recursion.
    if (tool_exe == tool_name) {
        std::string path = get_env("PATH");
        // Remove cmake-ctl bin path from PATH.
        size_t proxy_bin_pos = path.find("cmake-ctl\\bin");
        if (proxy_bin_pos == std::string::npos) proxy_bin_pos = path.find("cmake-ctl/bin");
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
    std::string command = "\"" + tool_exe + "\"";
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
