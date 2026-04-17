cmake_minimum_required(VERSION 3.15)
project(cmakectl-proxy)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Build the proxy executable
add_executable(cmakectl-proxy src/proxy/proxy.cpp)

# Platform-specific linking
if(WIN32)
    target_link_libraries(cmakectl-proxy PRIVATE shell32)
endif()

# Installation - copy to bin folder
install(TARGETS cmakectl-proxy DESTINATION ../bin)
