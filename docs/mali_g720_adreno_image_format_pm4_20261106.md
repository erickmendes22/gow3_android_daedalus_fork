# G720 vs Adreno: transition image churn and PM4 yield instrumentation
Driver 0c61ef0c, log GodOfWar3-Logs-20261106-141358.zip.
11.644-second transition: BC 207 creations / 932.80 MiB newly allocated,
RGBA128 254 creations / 494.60 MiB newly allocated. These are interval
allocation totals, not simultaneous video-memory peaks. BC creation max
218.80ms, RGBA128 creation max 204.64ms. Native Vulkan queue submit
max 0.12ms, submission throttle total 9.16ms over 506 measurements,
PM4 coroutine wall max 124.42ms even though it can include waits.
40 BC pool hits versus 344 misses and only 1 dropped entry, so a
higher pool quota alone is not supported.

Mali differs from Adreno in CPU AHB display and PanVK driver constraints;
the Mali profile forces max 2 Vulkan submissions, 0 prep workers and
1 compilation worker. Those settings have correctness or proven limited
throttle cost reasons; do not remove them without same-driver A/B.

This experiment caches exact immutable Vulkan getImageFormatProperties2
answers per thread and physical device on Mali only, including explicit
unsupported-format results. The original format, storage and ExtendedUsage
retry outcomes and supported sample count are preserved. Turnip and
non-Mali drivers use the original queries. pNext chains and transient
other-error outcomes are not cached. Set
GOW3_MALI_IMAGE_FORMAT_QUERY_CACHE=0 to opt out.

New independent timer fields distinguish image_format_query (actual
driver queries) from image_vk_allocate (vmaCreateImage call) and
pm4_resume_{blocked,work} (time in actual coroutine resume, not wall
between resumes). PM4 blocked yield reasons MemorySemaphore, Rewind,
WaitRegMem are sampled 1/256, no scheduling or wait semantics changed.

Device gate: on same driver and scene, verify if image_format_query time
vanishes but VMA allocation 200ms spikes remain; if so driver-side image
allocation is the main issue. Do not claim FPS increase from this
without phone measurements.
