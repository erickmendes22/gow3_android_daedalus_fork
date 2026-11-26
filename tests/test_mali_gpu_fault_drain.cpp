#include "video_core/buffer_cache/fault_result_policy.h"
using VideoCore::FaultResultCount;
static_assert(FaultResultCount(0,1024)==0);
static_assert(FaultResultCount(1,1024)==1);
static_assert(FaultResultCount(1023,1024)==1023);
static_assert(FaultResultCount(1024,1024)==1023);
static_assert(FaultResultCount(0xffffffff,1024)==1023);
static_assert(FaultResultCount(42,1)==0);
static_assert(FaultResultCount(42,0)==0);
int main() {}
