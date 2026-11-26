#include "video_core/renderer_vulkan/mali_index_bind_policy.h"
using Vulkan::CanonicalMaliDirectIndexBind;
static_assert(CanonicalMaliDirectIndexBind(4096, 2, 100, true).offset == 0);
static_assert(CanonicalMaliDirectIndexBind(4096, 2, 100, true).first_index == 2048);
static_assert(CanonicalMaliDirectIndexBind(4096, 4, 100, true).first_index == 1024);
static_assert(CanonicalMaliDirectIndexBind(4097, 2, 100, true).offset == 4097);
static_assert(CanonicalMaliDirectIndexBind(4096, 2, 100, false).offset == 4096);
static_assert(CanonicalMaliDirectIndexBind(0x1fffffffeull, 2, 2, true).offset == 0x1fffffffeull);
static_assert(CanonicalMaliDirectIndexBind(4096, 2, 0, true).offset == 4096);
int main() {}
