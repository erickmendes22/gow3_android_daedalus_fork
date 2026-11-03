// Verify exact source->destination byte mapping of the native readback coalescer.
// Test the same header used by the Android Vulkan renderer (not a copy of code).
#include "ports/sotc/android/sotc_readback_copy_coalesce.h"
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <random>
#include <utility>
#include <vector>

struct Copy { std::uint64_t srcOffset, dstOffset, size; };
using List=std::vector<Copy>;
using Map=std::vector<std::pair<std::uint64_t,std::uint64_t>>;

static Map Expand(const List& x) {
    Map out;
    for (auto c:x) {
        assert(c.size<=128);
        for (std::uint64_t n=0;n<c.size;++n) {
            out.emplace_back(c.dstOffset+n,c.srcOffset+n);
        }
    }
    return out;
}
static void Test(List x,std::size_t expected_merged) {
    const Map expected=Expand(x);
    const size_t old=x.size();
    const size_t joined=SotcReadback::CoalesceAdjacent(x);
    assert(joined==expected_merged);
    assert(x.size()+joined==old);
    assert(Expand(x)==expected);
    assert(SotcReadback::CoalesceAdjacent(x)==0);
}
int main() {
    Test({},0);
    Test({{0,64,16}},0);
    Test({{0,64,16},{16,80,8},{24,88,64}},2);
    Test({{0,64,16},{16,96,16}},0); // staging alignment padding
    Test({{0,64,16},{20,80,16}},0); // missing GPU source bytes
    Test({{0,64,16},{16,80,16},{48,112,16}},1); // do not bridge gaps
    Test({{0,64,16},{16,80,16},{24,96,16}},1); // overlapping source
    Test({{0,64,16},{16,80,16},{32,256,16},{48,272,16}},2);
    // Valid individual regions adjacent near max uint64_t, no offset overflow.
    constexpr auto max=std::numeric_limits<std::uint64_t>::max();
    Test({{max-32,max-40,8},{max-24,max-32,8}},1);
    std::mt19937_64 gen(0x51C02041ULL);
    for (int trial=0;trial<12000;++trial) {
        List v;
        std::uint64_t src=0,dst=0;
        const int n=1+int(gen()%64);
        for (int i=0;i<n;++i) {
            if (i && gen()%4!=0) src+=8*(gen()%3);
            if (i && gen()%4!=0) dst+=8*(gen()%4);
            const std::uint64_t sz=1+gen()%64;
            v.push_back({src,dst,sz});
            src+=sz;
            dst+=sz;
        }
        const Map original=Expand(v);
        const std::size_t count=v.size();
        const std::size_t joined=SotcReadback::CoalesceAdjacent(v);
        assert(joined<=count && v.size()+joined==count);
        assert(Expand(v)==original);
    }
    std::puts("PASS: 12000 randomized readback copy sequences preserve exact byte mapping and order");
}
