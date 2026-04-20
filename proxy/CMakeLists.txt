cmake_minimum_required(VERSION 3.15)
project(cmake-ctl-proxy)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(PROXY_VERSION "0.1.0")
if(DEFINED CMAKE_CTL_PROXY_VERSION AND NOT "${CMAKE_CTL_PROXY_VERSION}" STREQUAL "")
    set(PROXY_VERSION "${CMAKE_CTL_PROXY_VERSION}")
elseif(DEFINED ENV{CMAKE_CTL_PROXY_VERSION} AND NOT "$ENV{CMAKE_CTL_PROXY_VERSION}" STREQUAL "")
    set(PROXY_VERSION "$ENV{CMAKE_CTL_PROXY_VERSION}")
endif()

# Build the proxy executable from the proxy-owned source tree.
set(PROXY_SOURCE "src/proxy/proxy.cpp")
if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${PROXY_SOURCE}")
    # Backward-compatible fallback for older layouts.
    set(PROXY_SOURCE "../src/proxy/proxy.cpp")
endif()
add_executable(cmake-ctl-proxy ${PROXY_SOURCE})
target_compile_definitions(cmake-ctl-proxy PRIVATE CMAKE_CTL_PROXY_VERSION="${PROXY_VERSION}")

# Platform-specific linking
if(WIN32)
    target_link_libraries(cmake-ctl-proxy PRIVATE shell32)
endif()

# Install into repository bin artifact directory.
install(TARGETS cmake-ctl-proxy DESTINATION ../bin)
