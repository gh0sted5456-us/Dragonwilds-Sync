cmake_minimum_required(VERSION 3.22)
set(TARGET DragonLinkChat)
project(${TARGET})

add_library(${TARGET} SHARED src/main.cpp)
target_link_libraries(${TARGET} PUBLIC UE4SS)
set_target_properties(${TARGET} PROPERTIES OUTPUT_NAME "DragonLink-Chat")
