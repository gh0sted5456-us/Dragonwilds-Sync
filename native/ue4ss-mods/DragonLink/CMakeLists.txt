cmake_minimum_required(VERSION 3.22)
set(TARGET DragonLink)
project(${TARGET})

add_library(${TARGET} SHARED src/main.cpp)
target_link_libraries(${TARGET} PUBLIC UE4SS)
