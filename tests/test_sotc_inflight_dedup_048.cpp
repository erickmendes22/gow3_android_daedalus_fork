#include <cassert>
#include <cstdint>
#include <limits>
#include <vector>
#include "../ports/sotc/android/sotc_readback_dedup_048.h"
struct Arena { std::uint64_t cpu_addr; };
struct Copy { std::uint64_t srcOffset; std::uint64_t size; };
struct Item { const Arena* arena; std::vector<Copy> copies; };
int main() {
    const Arena a{0x100000}, b{0x300000};
    const std::vector<Item> one{{&a, {{0x1000, 0x100}}}};
    assert(SotcReadbackDedup::Covers(one,0x101000,8));
    assert(SotcReadbackDedup::Covers(one,0x1010f8,8));
    assert(!SotcReadbackDedup::Covers(one,0x1010f9,8));
    assert(!SotcReadbackDedup::Covers(one,0x100fff,8));
    assert(!SotcReadbackDedup::Covers(one,0x101000,0));
    const std::vector<Item> joined{{&a,{{0x1000,0x80},{0x1080,0x80}}}};
    assert(SotcReadbackDedup::Covers(joined,0x101070,0x30));
    const std::vector<Item> gap{{&a,{{0x1000,0x80},{0x1081,0x80}}}};
    assert(!SotcReadbackDedup::Covers(gap,0x101070,0x30));
    const std::vector<Item> twoArenas{{&a,{{0x1000,8}}},{&b,{{0x1000,8}}}};
    assert(!SotcReadbackDedup::Covers(twoArenas,0x101000,16));
    assert(SotcReadbackDedup::Covers(twoArenas,0x301000,8));
    assert(!SotcReadbackDedup::Covers(one,std::numeric_limits<uint64_t>::max()-1,8));
    return 0;
}
