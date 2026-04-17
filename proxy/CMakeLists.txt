cmake_minimum_required(VERSION 3.15)
project(cmake-ctl-proxy)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Build the proxy executable from the proxy-owned source tree.
set(PROXY_SOURCE "src/proxy/proxy.cpp")
if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${PROXY_SOURCE}")
    # Backward-compatible fallback for older layouts.
    set(PROXY_SOURCE "../src/proxy/proxy.cpp")
endif()
add_executable(cmake-ctl-proxy ${PROXY_SOURCE})

# Platform-specific linking
if(WIN32)
    target_link_libraries(cmake-ctl-proxy PRIVATE shell32)
endif()

# Install into repository bin artifact directory.
install(TARGETS cmake-ctl-proxy DESTINATION ../bin)
