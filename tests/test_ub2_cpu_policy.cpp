// SPDX-License-Identifier: GPL-2.0-or-later
#define GOW3_UB2_POLICY_TEST
#include "gow3_ub2_cpu_policy.h"
#include <cassert>
int main() {
    using namespace Gow3Ub2Cpu;
    cpu_set_t allowed{}, pair{};
    Scores scores{};
    for (int c=0;c<8;++c) { CPU_SET(c,&allowed); scores[c]=c<6?800:1024; }
    assert(SelectPrimePair(allowed,scores,pair));
    assert(CPU_COUNT(&pair)==2 && CPU_ISSET(6,&pair) && CPU_ISSET(7,&pair));
    scores[7]=0; assert(!SelectPrimePair(allowed,scores,pair));
    scores[7]=1000; assert(!SelectPrimePair(allowed,scores,pair));
    scores[7]=1024; CPU_CLR(7,&allowed); assert(!SelectPrimePair(allowed,scores,pair));
    CPU_SET(7,&allowed); scores.fill(1024); assert(!SelectPrimePair(allowed,scores,pair));
    CPU_ZERO(&allowed);
    for (int c : {2,4,8,10,12,15}) { CPU_SET(c,&allowed); scores[c]=(c==4||c==12)?2000:1000; }
    assert(SelectPrimePair(allowed,scores,pair));
    assert(CPU_ISSET(4,&pair) && CPU_ISSET(12,&pair));
    assert(!Get().enabled);
    return 0;
}
