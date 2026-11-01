// Independent executable regression of last-published vs last-consumed
// register deltas, including delayed draw consumption, writes that revert,
// first-seen zero values and ring-wrap ordering. No Vulkan functionality mocked.
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <deque>
#include <random>
#include <vector>
#include <cstdio>

using u32 = std::uint32_t;
constexpr unsigned Chunk = 64;
constexpr unsigned Chunks = 32;
constexpr unsigned Count = Chunk * Chunks;
struct Frame {
    std::vector<u32> packet;
    std::array<u32, Count> expected;
};
struct Queue {
    std::array<u32, Count> regs{};
    std::array<u32, Count> last{};
    std::array<u32, Count> consumed{};
    std::array<std::uint8_t, Chunks> valid{};
    std::array<std::uint8_t, Chunks> dirty{};
    std::deque<Frame> pending;
    unsigned sent = 0;
    unsigned skipped = 0;
    void Write(unsigned i, u32 value) {
        regs[i] = value;
        dirty[i / Chunk] = 1;
    }
    void Publish() {
        Frame f{{}, regs};
        for (unsigned chunk = 0; chunk < Chunks; ++chunk) {
            if (!dirty[chunk]) continue;
            const u32* src = regs.data() + chunk * Chunk;
            u32* previous = last.data() + chunk * Chunk;
            const bool changed = !valid[chunk] ||
                std::memcmp(src, previous, Chunk * sizeof(u32)) != 0;
            if (changed) {
                f.packet.push_back(chunk);
                f.packet.insert(f.packet.end(), src, src + Chunk);
                std::memcpy(previous, src, Chunk * sizeof(u32));
                valid[chunk] = 1;
                ++sent;
            } else {
                ++skipped;
            }
            dirty[chunk] = 0;
        }
        pending.push_back(std::move(f));
    }
    void Consume() {
        assert(!pending.empty());
        Frame f = std::move(pending.front());
        pending.pop_front();
        assert(f.packet.size() % (Chunk + 1) == 0);
        for (unsigned p = 0; p < f.packet.size(); p += Chunk + 1) {
            const unsigned chunk = f.packet[p];
            assert(chunk < Chunks);
            std::memcpy(consumed.data() + chunk * Chunk,
                        f.packet.data() + p + 1, Chunk * sizeof(u32));
        }
        assert(consumed == f.expected); // equivalent to an unoptimized full snapshot
    }
};
int main() {
    Queue q;
    q.Write(0, 0); // first-seen zero still transmitted
    q.Publish(); q.Consume();
    assert(q.sent == 1);
    q.Write(0, 0); // identical dirty block is redundant
    q.Publish(); q.Consume();
    assert(q.skipped == 1);
    // Last *published* is ahead of the consumer: skipping equal blocks is
    // correct only because all queued deltas remain FIFO ordered.
    q.Write(17, 123); q.Publish();
    q.Write(17, 123); q.Publish();
    q.Write(17, 991); q.Publish();
    q.Write(17, 123); q.Publish();
    while (!q.pending.empty()) q.Consume();
    std::mt19937 rng(0x5a17c);
    for (int i = 0; i < 50000; ++i) {
        for (int j = 0; j < 1 + (i % 19); ++j) {
            unsigned idx = rng() % Count;
            u32 value = (i % 3 == 0) ? q.regs[idx] : (rng() % 37);
            q.Write(idx, value);
        }
        if (i % 43 == 0) {
            // Equivalent to ClearState: every register becomes zero, all marked.
            q.regs.fill(0);
            q.dirty.fill(1);
        }
        q.Publish();
        if (q.pending.size() >= 511) q.Consume();
        if (i % 7 == 0 && !q.pending.empty()) q.Consume();
    }
    while (!q.pending.empty()) q.Consume();
    assert(q.sent > 0 && q.skipped > 100);
    std::printf("SotC register FIFO equivalence OK: sent=%u, skipped=%u\n",
                q.sent, q.skipped);
}
