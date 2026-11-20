"""Safety guards for the Mali background pipeline-cache warmup path.

These checks protect the native rendering code paths against accidentally
reintroducing live shader metadata into the background precompiler.
An actual ARM64 compilation is required separately by the same workflow.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERIAL = ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp"
COMPUTE = ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_compute_pipeline.h"


class MaliWarmupSafetyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = SERIAL.read_text(encoding="utf-8")
        cls.compute_code = COMPUTE.read_text(encoding="utf-8")

    def test_background_build_reads_snapshot_not_live_program(self):
        self.assertIn("stage->compile_info = std::make_unique<Shader::Info>(stage->program->info)", self.code)
        self.assertIn("stage->compile_info->user_data = {}", self.code)
        self.assertIn("const auto stage_refs = entry.stages;", self.code)
        self.assertIn("build_infos[i] = stage_refs[i]->compile_info.get()", self.code)
        self.assertIn("built.stage_refs = stage_refs;", self.code)
        self.assertIn("compute_key, *build_infos[0], modules[0]", self.code)
        self.assertIn("pipeline_cache, build_infos,", self.code)

    def test_published_pipelines_restore_live_stage_pointers(self):
        publish = self.code.index("for (auto& built : warm.built.Take(warm.mali ? 8 : 64))")
        rebind_graphics = self.code.index("built.graphics->PublishStages(built.live_infos)", publish)
        rebind_compute = self.code.index("built.compute->PublishStage(built.live_infos[0])", publish)
        insert = self.code.index("PublishFirst(graphics_pipelines", publish)
        self.assertLess(rebind_graphics, insert)
        self.assertLess(rebind_compute, insert)
        self.assertIn("void PublishStage(const Shader::Info* info)", self.compute_code)

    def test_reject_invalid_serialized_permutation(self):
        self.assertIn("stage.perm_idx >= Program::MaxPermutations", self.code)
        self.assertIn("entry.compute && (!infos[0] || !modules[0])", self.code)
        self.assertIn("std::ranges::none_of(modules", self.code)

    def test_mali_warmup_is_batched_without_dropping_entries(self):
        self.assertIn("warm.mali = mali;", self.code)
        self.assertIn("warm.mali && pump_started - warm.last_batch < 12ms", self.code)
        self.assertIn("warm.built.Take(warm.mali ? 2 : 64)", self.code)
        self.assertIn("warm.read.Take(warm.mali ? 2 : 32)", self.code)
        self.assertIn("now - warm.last_batch < (warm.mali ? 12ms : 4ms)", self.code)
        # No dropped entries: each completed compilation is published or
        # rejected through the original queue, with the desktop path intact.
        self.assertIn("warm.pool->Idle()", self.code)
        self.assertIn("warm.done.fetch_add(1, std::memory_order_relaxed)", self.code)
        self.assertIn("warm.pool->Push(", self.code)


    def test_cache_serialization_rejects_old_pointer_bearing_format(self):
        self.assertIn("ShaderMetaVersion = 9u", self.code)
        self.assertIn("Shader::UniformBufferLevel()", self.code)
        self.assertNotIn("info.Write(this, sizeof(InfoPersistent))", self.code)
        self.assertNotIn("info.Read(this, sizeof(Shader::InfoPersistent))", self.code)
        for name in ("buffers", "images", "samplers", "fmasks"):
            self.assertIn(f"info.Write({name});", self.code)
            self.assertIn(f"read_list({name},", self.code)
        self.assertIn("!spec.Deserialize(ar) || !info.Deserialize(ar)", self.code)

    def test_bad_cache_lengths_cannot_overflow_boost_resource_lists(self):
        self.assertIn("!ar.CanRead(count * sizeof(Item))", self.code)
        self.assertIn("read_list(buffers, NUM_BUFFERS)", self.code)
        self.assertIn("read_list(images, NUM_IMAGES * 4)", self.code)
        self.assertIn("read_list(samplers, NUM_SAMPLERS * 4)", self.code)
        self.assertIn("read_list(fmasks, NUM_FMASKS)", self.code)
        self.assertIn("!ar.CanRead(flat_size * sizeof(u32))", self.code)

    def test_cache_schema_migration_rejects_old_v7_boost_metadata(self):
        self.assertIn('Serialization::ShaderMetaVersion,', self.code)
        self.assertIn('Serialization::ShaderBinaryVersion,', self.code)
        self.assertIn('Serialization::PipelineKeyVersion,', self.code)
        self.assertIn('"gow3-cache-schema"', self.code)
        self.assertIn('GOW3_MALI_SHADER_SCHEMA status=reset-old-cache', self.code)
        self.assertIn('db.ArchiveIncompatibleCache()', self.code)
        self.assertIn('db.RestoreCompatibleArchive(', self.code)
        self.assertIn('if (restore_compatible_generation())', self.code)
        self.assertNotIn('db.Clear();', self.code)
        self.assertIn('save_profile_and_schema();', self.code)
        self.assertIn('db.Save(Storage::BlobType::ShaderProfile, "profile"', self.code)
        self.assertIn('mali_schema = !EmulatorSettings.IsPipelineCacheArchived()', self.code)

    def test_missing_profile_is_not_destructive_and_can_restore_archive(self):
        start = self.code.index('if (profile_data.empty()) {')
        end = self.code.index('if (profile_data.size() != sizeof(Shader::Profile))', start)
        cold_start = self.code[start:end]
        self.assertIn('const bool has_orphan_blobs =', cold_start)
        self.assertIn('if (has_orphan_blobs) {', cold_start)
        self.assertIn('db.ArchiveIncompatibleCache()', cold_start)
        self.assertIn('if (restore_compatible_generation())', cold_start)
        self.assertIn('GOW3_MALI_SHADER_CACHE status=restored-compatible-archive', cold_start)
        self.assertIn('GOW3_MALI_SHADER_CACHE status=new-profile', cold_start)
        self.assertIn('save_profile_and_schema();', cold_start)
        self.assertNotIn('db.Clear()', cold_start)
        # Cold driver-hash cache never adopts arbitrary existing .key files:
        # restoring an archive requires the exact profile AND schema match.
        storage = (ROOT / "gpu/shadps4/video_core/cache_storage.cpp").read_text()
        self.assertIn('matches_profile(candidate.path() / "profile.bin")', storage)
        self.assertIn('matches(candidate.path() / "gow3-cache-schema.bin", schema_bytes)', storage)
        self.assertIn('Shader::Profile previous{}, current{};', storage)
        self.assertIn('return previous == current;', storage)
        self.assertNotIn('matches(candidate.path() / "profile.bin", profile_bytes)', storage)

    def test_shader_cache_closure_drains_pending_writes(self):
        storage = (ROOT / "gpu/shadps4/video_core/cache_storage.cpp").read_text()
        self.assertIn('accepting_requests = false;', storage)
        self.assertIn('request_cv.notify_all();', storage)
        self.assertIn('io_worker.join(); // The worker drains every request', storage)
        self.assertIn('if (stoken.stop_requested()) {', storage)
        self.assertIn('if (!accepting_requests)', storage)
        self.assertNotIn('while (!stoken.stop_requested())', storage)
        self.assertNotIn('num_requests', storage)

    def test_missing_profile_does_not_log_filesystem_open_error(self):
        storage = (ROOT / "gpu/shadps4/video_core/cache_storage.cpp").read_text()
        begin = storage.index('void LoadVector(BlobType type,')
        end = storage.index('bool DataBase::Save(', begin)
        loader = storage[begin:end]
        self.assertIn('if (type == BlobType::ShaderProfile)', loader)
        self.assertIn('std::filesystem::exists(path, ec)', loader)
        self.assertIn('if (!ec && !present)', loader)
        self.assertLess(loader.index('if (!ec && !present)'),
                        loader.index('const auto file = IOFile{path, FileAccessMode::Read};'))
        self.assertIn('save_profile_and_schema();', self.code)
        # The new per-driver profile is based on actual physical-device
        # capabilities, never an invented default profile with stale shaders.
        self.assertNotIn('Shader::Profile fake_profile', self.code)

    def test_archive_is_non_destructive_and_restorable(self):
        storage = (ROOT / "gpu/shadps4/video_core/cache_storage.cpp").read_text()
        self.assertIn('bool DataBase::ArchiveIncompatibleCache()', storage)
        self.assertIn('bool DataBase::RestoreCompatibleArchive(', storage)
        self.assertIn('std::filesystem::rename(entry.path(), archive', storage)
        self.assertIn('std::filesystem::rename(file, dest, ec)', storage)
        self.assertIn('file.path().extension()', storage)
        self.assertNotIn('std::filesystem::remove(entry.path()', storage)

    def test_keeps_background_warmup_and_private_mali_driver_cache(self):
        self.assertIn("return StartBackgroundWarmUp();", self.code)
        self.assertIn("warm.mali_worker_cache", self.code)


if __name__ == "__main__":
    unittest.main()
