#include "ports/sotc/android/sotc_inflight_readback_bounds.h"
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <random>
#include <vector>

using U=std::uint64_t;
struct Copy {U addr{},size{};};
struct Item {U addr{},size{};std::vector<Copy> gpu_copies;};
struct Readback {
    U lo{},hi{};
    bool dirty{};
    std::vector<Item> items;
};
static bool OldOverlap(U a,U n,U b,U m) {
    return n != 0 && m != 0 && a < b+m && b < a+n;
}
static bool OldDirty(const Readback& r,U addr,U size) {
    bool dirty=r.dirty;
    for(auto& x:r.items) dirty|=OldOverlap(addr,size,x.addr,x.size);
    return dirty;
}
static bool NewDirty(const Readback& r,U addr,U size) {
    if(r.dirty) return true;
    if(!SotcInflight::Overlaps(addr,size,r.lo,r.hi-r.lo))return false;
    for(auto& x:r.items)if(SotcInflight::Overlaps(addr,size,x.addr,x.size))return true;
    return false;
}
static int OldFind(const std::vector<Readback>& all,U addr,U size) {
    for(int i=0;i<(int)all.size();++i)
        for(auto& x:all[i].items)
            for(auto& c:x.gpu_copies)
                if(OldOverlap(addr,size,c.addr,c.size))return i;
    return -1;
}
static int NewFind(const std::vector<Readback>& all,U addr,U size) {
    for(int i=0;i<(int)all.size();++i) {
        auto& r=all[i];
        if(!SotcInflight::Overlaps(addr,size,r.lo,r.hi-r.lo))continue;
        for(auto& x:r.items)
            for(auto& c:x.gpu_copies)
                if(OldOverlap(addr,size,c.addr,c.size))return i;
    }
    return -1;
}
int main() {
    static_assert(SotcInflight::Overlaps(10,5,14,1));
    static_assert(!SotcInflight::Overlaps(10,5,15,1));
    static_assert(!SotcInflight::Overlaps(10,0,10,5));
    static_assert(SotcInflight::Overlaps(UINT64_MAX-3,3,UINT64_MAX-1,1));
    std::mt19937_64 rnd{0x515442044};
    U excluded=0,scanned=0;
    for(int iteration=0;iteration<7500;++iteration) {
        std::vector<Readback> all;
        const int n=1+int(rnd()%30);
        for(int ri=0;ri<n;++ri) {
            Readback r;
            r.dirty=(rnd()%7==0);
            r.lo=~U{0};r.hi=0;
            const int count=1+int(rnd()%8); // includes SOTC_RB_HOT extra items
            for(int k=0;k<count;++k) {
                const U base=(rnd()%20000)*4096;
                const U length=4096*(1+rnd()%16);
                Item item{base,length,{}};
                r.lo=std::min(r.lo,base);r.hi=std::max(r.hi,base+length);
                for(int c=0;c<4;++c) {
                    // Page copies can extend slightly beyond the item window.
                    const U offset=(rnd()%16)*4096;
                    const U start=base+offset-(rnd()%3==0 && base>4096 ? 4096 : 0);
                    const U bytes=4096+((rnd()%3==0)?4096:0);
                    item.gpu_copies.push_back({start,bytes});
                    r.lo=std::min(r.lo,start);
                    r.hi=std::max(r.hi,start+bytes);
                }
                r.items.push_back(item);
            }
            all.push_back(std::move(r));
        }
        for(int q=0;q<30;++q) {
            U addr=(rnd()%20000)*4096;
            U size=(rnd()%4)*4096;
            for(const auto& r:all) {
                assert(OldDirty(r,addr,size)==NewDirty(r,addr,size));
                ++scanned;
                if(!SotcInflight::Overlaps(addr,size,r.lo,r.hi-r.lo))++excluded;
            }
            assert(OldFind(all,addr,size)==NewFind(all,addr,size));
        }
    }
    std::printf("PASS: 225000 queries across %llu inflight candidates, %llu conservative rejections; identical dirty/Find semantics\n",
      (unsigned long long)scanned,(unsigned long long)excluded);
}
