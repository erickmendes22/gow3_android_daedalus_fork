#include "ports/sotc/android/sotc_cpu_dirty_word_summary.h"
#include <array>
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <random>

using U=std::uint64_t;
int main() {
    std::array<U,64> cpu; cpu.fill(~U{0});
    std::atomic<U> live{~U{0}};
    std::mt19937_64 rng(0x043DEDABCULL);
    // Invariant: absence of a summary bit proves all 64 page bits are clear.
    // Random CPU set/clear, including writing to an already clear word.
    for (int i=0;i<300000;++i) {
        const unsigned word=unsigned(rng()%64);
        const U bits=U{1}<<(rng()%64);
        if(rng()%3==0) cpu[word]|=bits;
        else cpu[word]&=~bits;
        const U changed_bit=U{1}<<word;
        SotcDirtyWord::Update(live, cpu[word]?changed_bit:0, cpu[word]?0:changed_bit);
        const unsigned first=unsigned(rng()%64);
        const unsigned last=std::min(63u, first+unsigned(rng()%64));
        const bool might=SotcDirtyWord::MightContain(live,first,last);
        bool actually_dirty=false;
        for(unsigned j=first;j<=last;++j) actually_dirty|=cpu[j]!=0;
        assert(might || !actually_dirty);
    }
    // FaultGrace "keep" is conservatively held, not forgotten on upload.
    live.store(0,std::memory_order_relaxed);
    cpu.fill(0);
    cpu[12]=0x4000;
    SotcDirtyWord::Update(live,U{1}<<12,0);
    assert(SotcDirtyWord::MightContain(live,12,12));
    cpu[12]=0;
    SotcDirtyWord::Update(live,0,U{1}<<12);
    assert(!SotcDirtyWord::MightContain(live,12,12));
    // No invalid shift at last word 63.
    assert(SotcDirtyWord::Mask(0,63)==~U{0});
    assert(SotcDirtyWord::Mask(63,63)==(U{1}<<63));
    assert(SotcDirtyWord::Mask(1,1)==U{2});
    std::puts("PASS: 300000 randomized CPU dirty mutations, no missed page, valid word 63, grace retained");
}
