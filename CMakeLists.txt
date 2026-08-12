cmake_minimum_required(VERSION 3.18)
project(cliphub_native LANGUAGES CXX)

find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(_cliphub_native native/cliphub_native.cpp)
target_compile_features(_cliphub_native PRIVATE cxx_std_17)

if(MSVC)
  target_compile_options(_cliphub_native PRIVATE /O2 /W4)
else()
  target_compile_options(_cliphub_native PRIVATE -O3 -Wall -Wextra -Wpedantic)
endif()

install(TARGETS _cliphub_native LIBRARY DESTINATION . RUNTIME DESTINATION .)
