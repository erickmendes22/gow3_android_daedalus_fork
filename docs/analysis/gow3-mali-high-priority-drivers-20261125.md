# Mali performance tester — exact 1023daf52 lineage
This signed experimental APK adds independent, exact upstream ICDs:
- MineGraph panvk.8, SHA e71e23cdd2ddf52f72d7c348b5754df323cd56fbe6e0087b4c5c9b116565be4b. Its shipped driver code implements compatible draw batching, upload/decoded-texture reuse, tiler heap tuning, KRAID, duplicate binding/wait reduction. No cross-driver binary mixing. Keep speculative dead draws, load/clear elision and low-quality flags off; leave compatible batching in upstream implementation.
- JimVulkan R10, SHA 7e97db4d79d81ec9461d1e0676b62a865561cb56e21c151693aa25ffbe749f1c. Includes upstream CSF render-target reuse fixes, query wait improvements, shader cache, tessellation/geometry support. G720 MC12 upstream testing is not proof on G720 MC7.
- V4 remains selectable; native layouts are in upstream V4, v11-only vectorization is not asserted on v12. V3 remains automatic baseline.
- For explicitly selected newer drivers, prepare known compatible cached pipeline keys on the established private-cache worker before gameplay (six-second startup pump budget; unfinished tasks continue asynchronously). No blocking join or stale-cache synchronous loader. Existing disk shader index is retained for other profiles. Does not generate an offline raw GCN replay manifest or promise first-run cache coverage: actual GoW3 shader replay inputs and file locations are still needed. 
- Existing per-driver SHA namespace, real Shader::Profile and cache schema checks remain intact. No changes to Adreno or earlier freeze-fix commits.
- APK CI verifies signed output and embedded driver SHA values. Same save, driver selection and warm/cold cache logs needed for real performance and stability.
Sources: https://github.com/MineGraph-bilibili/panvk-Android/releases/download/Mesa.26.3.0-panvk.8/Mesa.26.3.0-panvk.8.zip
https://github.com/JimVulkan/mali-panvk/releases/download/v1.6.0/mali-panvk-27.0.0-devel-r10.zip
