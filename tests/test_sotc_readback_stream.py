#!/usr/bin/env python3
"""Compile the actual pinned SotC ReadbackWindow method in a tiny C++ harness.
Checks progressive 64/128/256/512 KiB windows, arena bounds and safe fallback.
It measures number of GPU syncs on a sequential dirty-page model, NOT FPS.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
ORIGINAL=ROOT/"upstream-sotc/gpu/shadps4/video_core/buffer_cache/buffer_cache.cpp"

class SotcReadbackStream(unittest.TestCase):
    def test_android_defaults_and_optout(self):
        shell=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
        gui=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
        java=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
        ini=(ROOT/"ports/sotc/android/package_sotc_runtime.py").read_text()
        self.assertIn('values["sotc_rb_stream"]?:"1"',gui)
        self.assertIn('save("sotc_rb_stream",if(it)"1" else "0")',gui)
        self.assertIn('env.put("SOTC_RB_STREAM",',java)
        self.assertIn('env.put("SOTC_RB_STREAM_MAX_KB",',java)
        self.assertIn('values["sotc_rb_stream_max_kb"]?:"512"',gui)
        self.assertIn('sotc_rb_stream_max_kb=512',ini)
        self.assertIn("sotc_rb_stream=1",ini)
        self.assertIn("SOTC_RB_STREAM="+chr(36)+"{SOTC_RB_STREAM:-1}",shell)
        self.assertIn("SOTC_RB_STREAM_MAX_KB="+chr(36)+"{SOTC_RB_STREAM_MAX_KB:-512}",shell)
        self.assertIn('if [ "$BB_READBACKS" != "2" ]; then export SOTC_RB_STREAM=0; fi',shell)
        self.assertIn("SOTC_VM_RANGE_CACHE="+chr(36)+"{SOTC_VM_RANGE_CACHE:-1}",shell)
        self.assertIn("BB_READBACKS="+chr(36)+"{BB_READBACKS:-2}",shell)

    @unittest.skipUnless(ORIGINAL.is_file(),"Pinned original SotC source checkout needed")
    def test_real_cpp_readback_window_and_sequential_sync_count(self):
        cpp=ORIGINAL.read_text()
        marker="std::pair<VAddr, VAddr> BufferCache::ReadbackWindow("
        start=cpp.index(marker)
        begin=cpp.index("{",start)
        depth=0
        end=None
        for i in range(begin,len(cpp)):
            if cpp[i]=="{":depth+=1
            elif cpp[i]=="}":
                depth-=1
                if depth==0:
                    end=i+1
                    break
        self.assertIsNotNone(end)
        function=cpp[start:end]
        for required in ("stream != 0", "rb_narrow_window == 0", "std::max<VAddr>",
                         "std::min<VAddr>", "const VAddr arena_end"):
            self.assertIn(required,function)
        self.assertIn('std::getenv("SOTC_RB_STREAM")',cpp)
        self.assertIn('std::getenv("SOTC_RB_STREAM_MAX_KB")',cpp)
        # The GPU->guest readback implementation must still include its heap
        # guard, no speculative out-of-order writes or modified-page bypass.
        self.assertIn("GatherDownloads(",cpp)
        self.assertIn("ApplyDownloads(",cpp)
        prolog=r"""
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <utility>
using u64=uint64_t;
using VAddr=uint64_t;
constexpr u64 operator ""_KB(unsigned long long v) { return v*1024ULL; }
constexpr u64 BYTES_PER_PAGE=4096;
namespace Common {
template<class T> T AlignDown(T x,T a) {return x&~(a-1);}
template<class T> T AlignUp(T x,T a) {return (x+a-1)&~(a-1);}
}
namespace SotcStats {
constexpr bool kFpsLog=false;
std::atomic<u64> rb_narrow_kept_bytes{0};
}
struct Buffer {VAddr cpu_addr; u64 size_bytes;};
struct Tracker {u64 CountGpuModifiedPages(VAddr,u64) {return 0;}};
class BufferCache {
public:
Tracker* memory_tracker;
u64 rb_narrow_window=64_KB;
std::pair<VAddr,VAddr> ReadbackWindow(const Buffer*,VAddr,u64,u64);
};
"""
        main=r"""
int main() {
    Tracker tracker;
    BufferCache bc{&tracker,64_KB};
    constexpr VAddr base=0x200000;
    constexpr u64 pages=128;
    Buffer arena{base,pages*64_KB};
    auto a=bc.ReadbackWindow(&arena,base,4096,0);
    assert(a.first==base && a.second==base+64_KB);
    auto b=bc.ReadbackWindow(&arena,base+64_KB,4096,512_KB);
    assert(b.first==base+64_KB && b.second==base+64_KB+512_KB);
    auto c=bc.ReadbackWindow(&arena,base+(pages-1)*64_KB,4096,512_KB);
    assert(c.second==base+pages*64_KB);
    auto count=[&](bool enabled) {
        BufferCache cache{&tracker,64_KB};
        u64 stream_end=0,stream_size=0,covered=0,waits=0,bytes=0;
        for(u64 p=0;p<pages;++p) {
            if(p<covered)continue; // page read-protection already removed
            const VAddr addr=base+p*64_KB;
            u64 stream=0;
            if(enabled) {
                if(addr>=stream_end && addr<stream_end+64_KB && stream_size)
                    stream_size=std::min(stream_size*2,512_KB);
                else stream_size=64_KB;
                stream_end=addr+stream_size;
                stream=stream_size>64_KB?stream_size:0;
            }
            const auto window=cache.ReadbackWindow(&arena,addr,4096,stream);
            assert(window.first>=base && window.second<=base+pages*64_KB);
            assert(window.second-window.first<=512_KB);
            bytes+=window.second-window.first;
            covered=(window.second-base)/64_KB;
            ++waits;
        }
        return std::pair<u64,u64>{waits,bytes};
    };
    const auto original=count(false);
    const auto sequential=count(true);
    assert(original.first==pages);
    assert(sequential.first < pages/3);
    assert(original.second==sequential.second);
    std::printf("SotC original C++ window: plain=%llu streamed=%llu, transferred_bytes=%llu\n",
        (unsigned long long)original.first,
        (unsigned long long)sequential.first,
        (unsigned long long)sequential.second);
}
"""
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"stream.cpp"
            source.write_text(prolog+function+"\n"+main)
            exe=Path(td)/"window"
            compiler=subprocess.run(["c++","-std=c++20","-O2","-Wall","-Wextra","-Werror",
                                    str(source),"-o",str(exe)],capture_output=True,text=True)
            self.assertEqual(compiler.returncode,0,compiler.stderr)
            result=subprocess.run([str(exe)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            print(result.stdout.strip())

if __name__=="__main__":
    unittest.main()
