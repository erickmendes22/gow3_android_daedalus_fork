#include "video_core/buffer_cache/dma_arena_chunk.h"
#include <cassert>
#include <cstdint>
using VideoCore::DmaArenaChunk;
int main() {
    constexpr std::uint64_t M=1024*1024, B=64*1024, base=0x1040000000ull;
    // A merged guest resident interval crosses three distinct arenas.
    auto addr=base+31*M;
    const auto end=base+65*M;
    auto n=DmaArenaChunk(addr,end,base,32*M,B);
    assert(n==M); addr+=n;
    n=DmaArenaChunk(addr,end,base+32*M,32*M,B);
    assert(n==32*M); addr+=n;
    n=DmaArenaChunk(addr,end,base+64*M,32*M,B);
    assert(n==M); addr+=n; assert(addr==end);
    // Same two pages already migrated into a single actual VkBuffer.
    assert(DmaArenaChunk(base+31*M,base+33*M,base,64*M,B)==2*M);
    assert(DmaArenaChunk(base+32*M,end,base,32*M,B)==0);
    assert(DmaArenaChunk(base,base+1,base,32*M,B)==0);
    assert(DmaArenaChunk(base,base+8ull*1024*M,base,8ull*1024*M,B)==0xffff0000u);
}
