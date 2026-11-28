// SPDX-License-Identifier: GPL-2.0-or-later
#include "video_core/renderer_vulkan/host_copy_wait.h"
#include <cassert>
#include <thread>
#include <vector>
int main() {
    using Vulkan::Detail::HostCopyCompletion;
    for (unsigned repeat=0; repeat<20; ++repeat) {
        HostCopyCompletion completion;
        constexpr unsigned N=12000;
        std::vector<unsigned> data(N+1);
        std::jthread writer([&] {
            for (unsigned i=1;i<=N;++i) {
                data[i]=i;
                completion.Publish(i);
                if (i%17==0) std::this_thread::yield();
            }
        });
        std::jthread reader([&] {
            for (unsigned i=1;i<=N;i+=3) {
                completion.Wait(i);
                assert(completion.Value()>=i);
                assert(data[i]==i);
            }
        });
        for (unsigned i=1;i<=N;i+=7) {
            completion.Wait(i);
            assert(completion.Value()>=i);
            assert(data[i]==i);
        }
        completion.Wait(N);
        assert(data[N]==N);
        writer.join();
        reader.join();
        completion.Wait(N); // already complete: no notification required
    }
}
