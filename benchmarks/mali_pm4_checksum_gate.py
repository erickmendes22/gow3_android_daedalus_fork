#!/usr/bin/env python3
"""Benchmark the *actual* Liverpool::HashRegisterPacket implementation on the host.

Do not infer device FPS from host C++ timings: absence of observed PM4
register words/frame prevents a numeric FPS claim. Instead report the
required words/frame for a 10 ms reduction, grounded in the existing G615
frame-time gate. Does not build an APK.
"""
from pathlib import Path
import json
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'gpu/shadps4/video_core/amdgpu/liverpool.cpp'
FIXTURE = ROOT / 'benchmarks/fixtures/mali_g615_20261105_152530.json'


def actual_hash_source():
    src = SRC.read_text()
    marker = 'u64 Liverpool::HashRegisterPacket('
    start = src.index(marker)
    end = src.index('\n}', start) + 2
    return src[start:end]


def run(iterations=75000, words=64):
    if words < 1 or words > 1024 or iterations < 1000:
        raise ValueError('invalid benchmark dimensions')
    impl = actual_hash_source()
    cpp = r'''
#include <array>
#include <atomic>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>
using u64 = std::uint64_t;
using u32 = std::uint32_t;
struct Liverpool { static u64 HashRegisterPacket(u64 checksum, const u32* words, u32 count); };
''' + impl + r'''
using Clock = std::chrono::steady_clock;
std::atomic<u64> sink{0};
double measure(bool enabled, unsigned n, unsigned words) {
  std::array<u32, 1024> data{};
  for (unsigned i=0;i<words;++i) data[i] = 0x9e3779b9u * (i+1);
  u64 checksum = 0x123456789abcdef0ULL;
  const auto began=Clock::now();
  for (unsigned i=0;i<n;++i) {
    if (enabled) checksum = Liverpool::HashRegisterPacket(checksum,data.data(),words);
    std::atomic_signal_fence(std::memory_order_seq_cst);
  }
  const auto end=Clock::now();
  sink.fetch_xor(checksum, std::memory_order_relaxed);
  return std::chrono::duration<double,std::nano>(end-began).count()/n;
}
double median(std::vector<double> a) {
  std::sort(a.begin(),a.end());
  return a[a.size()/2];
}
int main(int argc, char** argv) {
  if(argc!=3) return 2;
  const unsigned n=std::strtoul(argv[1],nullptr,10);
  const unsigned words=std::strtoul(argv[2],nullptr,10);
  measure(true,n/2,words); measure(false,n/2,words);
  std::vector<double> old_values,new_values;
  for(unsigned r=0;r<9;++r) {
    if(r%2) {
      new_values.push_back(measure(false,n,words));
      old_values.push_back(measure(true,n,words));
    } else {
      old_values.push_back(measure(true,n,words));
      new_values.push_back(measure(false,n,words));
    }
  }
  std::printf("{\"old_ns_per_packet\":%.6f,\"new_ns_per_packet\":%.6f,"
              "\"words\":%u,\"samples\":9,\"checksum_sink\":%llu}\n",
              median(old_values),median(new_values), words,
              (unsigned long long)sink.load());
}
'''
    with tempfile.TemporaryDirectory(prefix='gow3-pm4-') as tmp:
        source = Path(tmp) / 'bench.cpp'
        exe = Path(tmp) / 'bench'
        source.write_text(cpp)
        subprocess.run([os.environ.get('CXX','c++'),'-std=c++20','-O3','-Wall',
                        '-Wextra','-Werror',str(source),'-o',str(exe)],check=True)
        return json.loads(subprocess.check_output(
            [str(exe),str(iterations),str(words)],text=True))


def analyze(result, fixture):
    saving_ns = max(0.0,result['old_ns_per_packet']-result['new_ns_per_packet'])
    if saving_ns < 0.01:
        return None
    target_ms = fixture['min_meaningful_ms_per_frame']
    packets_needed = target_ms * 1e6 / saving_ns
    return dict(saved_ns_per_packet=saving_ns,
                packets_per_frame_for_10ms=packets_needed,
                words_per_frame_for_10ms=packets_needed*result['words'],
                words_per_draw_for_10ms=packets_needed*result['words']/
                    fixture['draws_per_frame_est'])


if __name__=='__main__':
    data = run()
    fixture = json.loads(FIXTURE.read_text())
    report = analyze(data,fixture)
    print('SOURCE: real Liverpool::HashRegisterPacket compiled from liverpool.cpp')
    print('HOST AB:',json.dumps(data,sort_keys=True))
    print('BREAK-EVEN:',json.dumps(report,sort_keys=True))
    print('DECISION: NOT PROMOTED to APK: no observed PM4 packet-count/frame baseline; '
          'host hashing speed does not predict FEX/PanVK/Android FPS.')
