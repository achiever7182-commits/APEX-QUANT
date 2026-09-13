cmake_minimum_required(VERSION 3.21)

project(binance_testnet_bot LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(ixwebsocket CONFIG REQUIRED)
find_package(nlohmann_json CONFIG REQUIRED)
find_package(CURL REQUIRED)
find_package(OpenSSL REQUIRED)

add_executable(binance_testnet_bot main.cpp)

target_link_libraries(binance_testnet_bot PRIVATE
    ixwebsocket::ixwebsocket
    nlohmann_json::nlohmann_json
    CURL::libcurl
    OpenSSL::Crypto
)

if(WIN32)
    target_link_libraries(binance_testnet_bot PRIVATE bcrypt)

    target_compile_definitions(binance_testnet_bot PRIVATE
        NOMINMAX
        WIN32_LEAN_AND_MEAN
        _CRT_SECURE_NO_WARNINGS
    )
endif()

if(MSVC)
    target_compile_options(binance_testnet_bot PRIVATE /W4 /permissive-)
else()
    target_compile_options(binance_testnet_bot PRIVATE -Wall -Wextra -Wpedantic)
endif()
