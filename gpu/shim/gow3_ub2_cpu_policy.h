// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#if defined(__ANDROID__) || defined(GOW3_UB2_POLICY_TEST)
#include <array>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sched.h>
#include <time.h>
#include <unistd.h>

namespace Gow3Ub2Cpu {
// Only choose a confirmed two-CPU top tier; do not guess CPU numbers or override cpusets.
using Scores = std::array<unsigned long long, CPU_SETSIZE>;
inline bool SelectPrimePair(const cpu_set_t& allowed, const Scores& scores, cpu_set_t& prime) {
    CPU_ZERO(&prime);
    if (CPU_COUNT(&allowed) < 4) return false;
    unsigned long long best = 0;
    for (int cpu = 0; cpu < CPU_SETSIZE; ++cpu) {
        if (!CPU_ISSET(cpu, &allowed)) continue;
        if (!scores[cpu]) return false;
        if (scores[cpu] > best) best = scores[cpu];
    }
    for (int cpu = 0; cpu < CPU_SETSIZE; ++cpu) {
        if (CPU_ISSET(cpu, &allowed) && scores[cpu] == best) CPU_SET(cpu, &prime);
    }
    return CPU_COUNT(&prime) == 2 && CPU_COUNT(&allowed) > 2;
}

inline bool ReadScores(const cpu_set_t& allowed, const char* field, Scores& scores) {
    scores.fill(0);
    for (int cpu = 0; cpu < CPU_SETSIZE; ++cpu) {
        if (!CPU_ISSET(cpu, &allowed)) continue;
        char path[160];
        std::snprintf(path, sizeof(path), "/sys/devices/system/cpu/cpu%d/%s", cpu, field);
        std::FILE* f = std::fopen(path, "r");
        if (!f) return false;
        const bool ok = std::fscanf(f, "%llu", &scores[cpu]) == 1 && scores[cpu] != 0;
        std::fclose(f);
        if (!ok) return false;
    }
    return true;
}

struct Policy {
    cpu_set_t allowed{}, prime{};
    bool enabled = false;
    const char* source = "none";
};
inline const Policy& Get() {
    static const Policy p = [] {
        Policy result;
        const char* aot = std::getenv("BB_AOT");
        const char* opt = std::getenv("GOW3_UB2_PRIME_AFFINITY");
        if (!aot || !*aot || (opt && std::strcmp(opt, "0") == 0)) return result;
        if (sched_getaffinity(getpid(), sizeof(result.allowed), &result.allowed) != 0) return result;
        Scores scores{};
        for (const char* field : {"cpu_capacity", "cpufreq/cpuinfo_max_freq"}) {
            if (ReadScores(result.allowed, field, scores) &&
                SelectPrimePair(result.allowed, scores, result.prime)) {
                result.enabled = true;
                result.source = field;
                break;
            }
        }
        return result;
    }();
    return p;
}

inline bool SameMask(const cpu_set_t& a, const cpu_set_t& b) {
    for (int cpu = 0; cpu < CPU_SETSIZE; ++cpu)
        if (CPU_ISSET(cpu, &a) != CPU_ISSET(cpu, &b)) return false;
    return true;
}
inline void Report(const char* role, const char* status, const cpu_set_t& mask, const char* source) {
    // Single line so interleaved runtime logging cannot split the mask.
    char cpus[256]{};
    size_t pos = 0;
    for (int cpu = 0; cpu < CPU_SETSIZE && pos < sizeof(cpus)-8; ++cpu) {
        if (CPU_ISSET(cpu, &mask)) {
            const int n = std::snprintf(cpus+pos, sizeof(cpus)-pos, "%s%d", pos ? "," : "", cpu);
            if (n <= 0 || static_cast<size_t>(n) >= sizeof(cpus)-pos) break;
            pos += static_cast<size_t>(n);
        }
    }
    std::fprintf(stderr, "UB2_CPU_AFFINITY role=%s status=%s source=%s allowed=%s current_cpu=%d\n",
                 role, status, source, pos ? cpus : "none", sched_getcpu());
}
inline void ApplyPrimeAffinity(const char* role) {
    const auto& p = Get();
    if (!std::getenv("BB_AOT")) return;
    cpu_set_t current{};
    if (sched_getaffinity(0, sizeof(current), &current) != 0) return;
    if (!p.enabled || !SameMask(current, p.allowed)) {
        Report(role, "unchanged", current, p.source);
        return;
    }
    const int ret = sched_setaffinity(0, sizeof(p.prime), &p.prime);
    cpu_set_t effective = current;
    (void)sched_getaffinity(0, sizeof(effective), &effective);
    Report(role, ret == 0 && SameMask(effective, p.prime) ? "prime-pair" : "fallback", effective, p.source);
}

inline void ApplyToCommandProcessor() { ApplyPrimeAffinity("GpuComm"); }

// New named host workers may inherit the command processor's mask. Restore only
// a matching inherited mask; never change guest PS4 affinity or other masks.
inline void RestoreNamedHostWorker(const char* name) {
    if (std::strncmp(name, "gow3:", 5) != 0 && std::strncmp(name, "shadPS4:", 8) != 0) return;
    if (std::strcmp(name, "shadPS4:GpuCommandProcessor") == 0) return;
    const auto& p = Get();
    if (!p.enabled) return;
    cpu_set_t current{};
    if (sched_getaffinity(0, sizeof(current), &current) == 0 && SameMask(current, p.prime)) {
        (void)sched_setaffinity(0, sizeof(p.allowed), &p.allowed);
    }
}

inline unsigned long long Ns(clockid_t clock) {
    timespec t{};
    if (clock_gettime(clock, &t) != 0) return 0;
    return static_cast<unsigned long long>(t.tv_sec) * 1000000000ULL + t.tv_nsec;
}
inline void SampleThread(const char* role) {
    if (!std::getenv("BB_AOT")) return;
    static thread_local unsigned long long last_wall = 0, last_cpu = 0;
    const auto wall = Ns(CLOCK_MONOTONIC);
    if (!wall || (last_wall && wall-last_wall < 5000000000ULL)) return;
    const auto cpu = Ns(CLOCK_THREAD_CPUTIME_ID);
    if (last_wall && cpu >= last_cpu) {
        std::fprintf(stderr, "UB2_CPU_SAMPLE role=%s tid=%d current_cpu=%d thread_cpu_pct=%.1f\n",
                     role, static_cast<int>(gettid()), sched_getcpu(), 100.0 * (cpu-last_cpu)/(wall-last_wall));
    }
    last_wall = wall;
    last_cpu = cpu;
}
inline void SampleCommandProcessor() { SampleThread("GpuComm"); }
} // namespace Gow3Ub2Cpu
#endif
