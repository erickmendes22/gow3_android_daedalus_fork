#include <array>
#include <cassert>
#include <vector>
#include "video_core/buffer_cache/mali_copy_coalescing.h"
struct Copy {std::uint64_t srcOffset,dstOffset,size;};
using VideoCore::MergeAdjacentCopy;
constexpr bool exact() {Copy a{0,64,64}; return MergeAdjacentCopy(a,Copy{64,128,32}) && a.size==96;}
static_assert(exact());
constexpr bool no_gap() {Copy a{0,64,32}; return !MergeAdjacentCopy(a,Copy{32,128,32}) && !MergeAdjacentCopy(a,Copy{64,96,32});}
static_assert(no_gap());
constexpr bool overflow() {Copy a{~0ull-3,0,8};return !MergeAdjacentCopy(a,Copy{4,8,4});}
static_assert(overflow());
int main(){std::vector<Copy> c{{0,64,64},{64,128,64},{128,192,64},{512,256,64}};
assert(VideoCore::CoalesceAdjacentCopies(c)==2);assert(c.size()==2);assert(c[0].size==192);assert(c[1].srcOffset==512);}
