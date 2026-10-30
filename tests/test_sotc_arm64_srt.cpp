#include "../ports/sotc/android/srt_sotc_portable.h"
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <vector>
using namespace Shader::SotcArm64Srt;
namespace {
std::uint64_t base;
std::vector<std::uint8_t> mem;
const std::uint32_t* userdata=nullptr;
void read(std::uint32_t* dst, std::uint64_t src, std::uint64_t bytes) {
    std::memset(dst,0,std::size_t(bytes));
    if (src>=base && src-base<=mem.size() && bytes<=mem.size()-(src-base)) {
        std::memcpy(dst,mem.data()+(src-base),std::size_t(bytes));
    } else if (userdata && src>=reinterpret_cast<std::uintptr_t>(userdata) &&
               src-reinterpret_cast<std::uintptr_t>(userdata)<=16*sizeof(std::uint32_t) &&
               bytes<=16*sizeof(std::uint32_t)-
                      (src-reinterpret_cast<std::uintptr_t>(userdata))) {
        std::memcpy(dst,reinterpret_cast<const std::uint8_t*>(userdata)+
                        (src-reinterpret_cast<std::uintptr_t>(userdata)),std::size_t(bytes));
    }
}
void put32(std::size_t offset,std::uint32_t value) {
    assert(offset+4<=mem.size());std::memcpy(mem.data()+offset,&value,4);
}
void put64(std::size_t offset,std::uint64_t value) {
    assert(offset+8<=mem.size());std::memcpy(mem.data()+offset,&value,8);
}
}
int main() {
    mem.resize(8192);base=UINT64_C(0x30000000);
    put32(256+5*4,0xDEADBEEFu);
    std::uint32_t user[16]{};user[0]=std::uint32_t(base+256);user[1]=0;user[2]=1;
    userdata=user;
    // A pointer chain, dynamic scalar index, arithmetic and a 512-dword
    // fallback window all use the same guest copy callback.
    std::vector<std::uint32_t> instructions {
        Magic,1024,PushImm,0,UserData,2,Imm,4,Add,CopyDyn,20,
        CopyWindow,128,Pop,End
    };
    assert(Validate(instructions));
    std::vector<std::uint32_t> flat(1024,0);
    assert(Run(instructions,user,flat.data(),read));
    assert(flat[20]==0xDEADBEEFu && flat[128+5]==0xDEADBEEFu);
    // Null/unmapped SRT root must not read unsafe memory.
    user[0]=0;std::fill(flat.begin(),flat.end(),0xFFFFFFFFu);
    assert(Run(instructions,user,flat.data(),read));
    assert(flat[20]==0 && flat[128+5]==0);
    instructions[0]=0x42545253u; // reject GoW3 SRT cache from another project
    assert(!Validate(instructions));
    instructions[0]=Magic;
    instructions[1]=200; // window would overflow
    assert(!Validate(instructions));
    puts("SotC ARM64 portable SRT: valid chain, dynamic reads, window and unmapped memory PASS");
}
