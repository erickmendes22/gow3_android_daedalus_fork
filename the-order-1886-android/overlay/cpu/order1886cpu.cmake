# liborder1886cpu.so: guest_cpu.h on FEXCore, linked statically against FEX's libraries.
set(ORDER1886CPU_DIR "${CMAKE_CURRENT_LIST_DIR}")
add_library(order1886cpu SHARED "${ORDER1886CPU_DIR}/guest_cpu_fex.cpp" "${ORDER1886CPU_DIR}/host_call_arm64.S")
target_include_directories(order1886cpu PRIVATE "${ORDER1886CPU_DIR}/../src" "${CMAKE_SOURCE_DIR}/Source" "${CMAKE_BINARY_DIR}/generated")
target_link_libraries(order1886cpu PRIVATE FEXCore Common JemallocLibs fmt::fmt)
target_link_options(order1886cpu PRIVATE -Wl,--no-undefined)
target_compile_options(order1886cpu PRIVATE ${FEX_TUNE_COMPILE_FLAGS})
set_target_properties(order1886cpu PROPERTIES
  LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
  C_VISIBILITY_PRESET hidden
  CXX_VISIBILITY_PRESET hidden
  VISIBILITY_INLINES_HIDDEN TRUE)

if(ANDROID)
  # Embedded FEX runs no FEXServer. Its Linux IPC client also requires a noexcept
  # std::function assignment unsupported by libc++; keep it out of Android Common.
  # Adapted from Bloodborne-Android cpu/bbcpu.cmake at 2e472653.
  get_target_property(gow3_common_sources Common SOURCES)
  list(FILTER gow3_common_sources EXCLUDE REGEX "FEXServerClient\\.cpp$")
  set_target_properties(Common PROPERTIES SOURCES "${gow3_common_sources}")
endif()
if(ANDROID)
  target_compile_options(FEXCore_Base PRIVATE -include "${ORDER1886CPU_DIR}/bionic_compat.h")
endif()
