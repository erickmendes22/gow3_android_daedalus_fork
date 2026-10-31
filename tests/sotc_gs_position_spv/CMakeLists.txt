cmake_minimum_required(VERSION 3.24)
project(sotc_gs_position_test LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
if (NOT GPU_SOURCE)
  message(FATAL_ERROR "Set -DGPU_SOURCE=path/to/staged/sotc/gpu")
endif()
set(SIRIT_TESTS OFF CACHE BOOL "" FORCE)
set(SIRIT_USE_SYSTEM_SPIRV_HEADERS OFF CACHE BOOL "" FORCE)
add_subdirectory(${GPU_SOURCE}/third_party/sirit ${CMAKE_BINARY_DIR}/sirit)
add_executable(sotc-gs-position-test
  ${CMAKE_CURRENT_SOURCE_DIR}/../test_sotc_gs_position_spv.cpp
  ${GPU_SOURCE}/shadps4/shader_recompiler/backend/spirv/emit_spirv_quad_rect.cpp)
target_include_directories(sotc-gs-position-test PRIVATE
  ${GPU_SOURCE}/shadps4
  ${GPU_SOURCE}/shim
  ${GPU_SOURCE}/third_party/gcn/include
  ${GPU_SOURCE}/third_party/half/include
  ${GPU_SOURCE}/third_party/magic_enum/include
  ${GPU_SOURCE}/third_party/imgui)
target_compile_options(sotc-gs-position-test PRIVATE -ffunction-sections -fdata-sections)
target_link_options(sotc-gs-position-test PRIVATE -Wl,--gc-sections)
target_link_libraries(sotc-gs-position-test PRIVATE sirit)
