cmake_minimum_required(VERSION 3.15)
project(cmake-ctl-proxy)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Build the proxy executable
add_executable(cmake-ctl-proxy src/proxy/proxy.cpp)

# Platform-specific linking
if(WIN32)
    target_link_libraries(cmake-ctl-proxy PRIVATE shell32)
endif()

# Installation - copy to bin folder
install(TARGETS cmake-ctl-proxy DESTINATION ../bin)
