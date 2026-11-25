// SPDX-FileCopyrightText: Copyright 2025-2026 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include "common/elf_info.h"
#include "common/io_file.h"
#include "common/polyfill_thread.h"
#include "common/thread.h"
#include "core/emulator_settings.h"
#include "shader_recompiler/profile.h"

#include "video_core/cache_storage.h"
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/renderer_vulkan/vk_pipeline_cache.h"

#include <miniz.h>

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <condition_variable>
#include <cstring>
#include <type_traits>
#include <functional>
#include <future>
#include <mutex>
#include <queue>
#include <string>
#include <system_error>

namespace {

std::condition_variable_any request_cv{};
std::queue<std::packaged_task<void()>> req_queue{};
std::mutex m_request{};
bool accepting_requests{}; // protected by m_request, including Close()

mz_zip_archive zip_ar{};
bool ar_is_read_only{true};

} // namespace

namespace Storage {

void ProcessIO(const std::stop_token& stoken) {
    Common::SetCurrentThreadName("shadPS4:PipelineCacheIO");

    for (;;) {
        std::packaged_task<void()> request{};
        {
            std::unique_lock lock{m_request};
            Common::CondvarWait(request_cv, lock, stoken,
                                [&] { return !req_queue.empty(); });
            if (req_queue.empty()) {
                // Stop only after the last accepted shader/profile write.
                if (stoken.stop_requested()) {
                    break;
                }
                continue;
            }
            request = std::move(req_queue.front());
            req_queue.pop();
        }
        if (request.valid()) {
            request();
        }
    }
}

constexpr std::string GetBlobFileExtension(BlobType type) {
    switch (type) {
    case BlobType::ShaderMeta: {
        return "meta";
    }
    case BlobType::ShaderBinary: {
        return "spv";
    }
    case BlobType::PipelineKey: {
        return "key";
    }
    case BlobType::ShaderProfile: {
        return "bin";
    }
    default:
        UNREACHABLE();
    }
}

void DataBase::Open() {
    if (opened) {
        return;
    }

    const auto& game_info = Common::ElfInfo::Instance();

    using namespace Common::FS;
    if (EmulatorSettings.IsPipelineCacheArchived()) {
        mz_zip_zero_struct(&zip_ar);

        cache_path = GetUserPath(PathType::CacheDir) /
                     std::filesystem::path{game_info.GameSerial()}.replace_extension(".zip");

        if (!mz_zip_reader_init_file(&zip_ar, cache_path.string().c_str(),
                                     MZ_ZIP_FLAG_READ_ALLOW_WRITING) ||
            !mz_zip_validate_archive(&zip_ar, 0)) {
            LOG_INFO(Render, "Cache archive {} is not found or archive is corrupted",
                     cache_path.string().c_str());
            mz_zip_reader_end(&zip_ar);
            mz_zip_writer_init_file(&zip_ar, cache_path.string().c_str(), 0);
        }
    } else {
        const auto legacy_path = GetUserPath(PathType::CacheDir) / game_info.GameSerial();
        cache_path = legacy_path;
        // The uploaded G720 log switches between different PanVK driver
        // archives. Their Shader::Profile capabilities differ; a single
        // shared cache directory caused CheckCacheProfile() to erase hundreds
        // of the other driver's cached SPIR-V and pipeline keys each switch.
        // Use the import's 64-hex SHA-256 folder name as a stable namespace.
        // No arbitrary environment path is appended to the user cache path.
        if (const char* driver = std::getenv("GOW3_VULKAN_DRIVER")) {
            const std::filesystem::path driver_path{driver};
            const auto driver_id = driver_path.parent_path().filename().string();
            const bool panvk = driver_path.filename() == "libvulkan_panfrost.so";
            const bool valid_id = driver_id.size() == 64 &&
                std::all_of(driver_id.begin(), driver_id.end(), [](unsigned char c) {
                    return std::isxdigit(c) != 0;
                });
            if (panvk && valid_id) {
                cache_path = legacy_path / ("panvk-" + driver_id);
            }
        }
        const bool first_driver_open = cache_path != legacy_path &&
                                       !std::filesystem::exists(cache_path);
        std::filesystem::create_directories(cache_path);
        if (first_driver_open && std::filesystem::exists(legacy_path)) {
            // Copy legacy metadata once, never move it: CheckCacheProfile()
            // will discard incompatible profiles but can preserve a valid
            // matching cache after updating from the previous APK.
            u32 migrated = 0;
            std::error_code error;
            for (const auto& entry : std::filesystem::directory_iterator{legacy_path, error}) {
                if (error || !entry.is_regular_file(error)) continue;
                const auto ext = entry.path().extension();
                if (ext != ".spv" && ext != ".key" && ext != ".meta" &&
                    entry.path().filename() != "profile.bin")
                    continue;
                std::filesystem::copy_file(entry.path(),
                    cache_path / entry.path().filename(),
                    std::filesystem::copy_options::skip_existing, error);
                if (!error) ++migrated;
                error.clear();
            }
            LOG_INFO(Render, "PanVK per-driver shader cache: migrated {} legacy blobs", migrated);
        }
    }

    {
        std::scoped_lock lock{m_request};
        accepting_requests = true;
    }
    io_worker = std::jthread{ProcessIO};
    opened = true;
}

void DataBase::Close() {
    if (!IsOpened()) {
        return;
    }

    {
        std::scoped_lock lock{m_request};
        accepting_requests = false;
    }
    opened = false;
    io_worker.request_stop();
    request_cv.notify_all();
    io_worker.join(); // The worker drains every request before exiting.

    if (EmulatorSettings.IsPipelineCacheArchived()) {
        mz_zip_writer_finalize_archive(&zip_ar);
        mz_zip_writer_end(&zip_ar);
    }

    LOG_INFO(Render, "Shader cache writes flushed and database closed");
}

template <typename T>
bool WriteVector(const BlobType type, std::filesystem::path&& path_, std::vector<T>&& v) {
    {
        auto request = std::packaged_task<void()>{[=]() {
            auto path{path_};
            path.replace_extension(GetBlobFileExtension(type));
            if (EmulatorSettings.IsPipelineCacheArchived()) {
                ASSERT_MSG(!ar_is_read_only,
                           "The archive is read-only. Did you forget to call `FinishPreload`?");
                if (!mz_zip_writer_add_mem(&zip_ar, path.string().c_str(), v.data(),
                                           v.size() * sizeof(T), MZ_BEST_COMPRESSION)) {
                    LOG_ERROR(Render, "Failed to add {} to the archive", path.string().c_str());
                }
            } else {
                // gow3: write beside and rename into place, so a game that ends during the
                // write never leaves a truncated blob if a process is forcibly killed.
                using namespace Common::FS;
                auto temp{path};
                temp += ".tmp";
                {
                    const auto file = IOFile{temp, FileAccessMode::Create};
                    if (!file.IsOpen() || file.Write(v) != v.size()) {
                        return;
                    }
                }
                std::error_code error;
                std::filesystem::rename(temp, path, error);
            }
        }};
        std::scoped_lock lock{m_request};
        if (!accepting_requests) {
            return false; // Close has started; never enqueue after the drain.
        }
        req_queue.emplace(std::move(request));
    }

    request_cv.notify_one();
    return true;
}

template <typename T>
void LoadVector(BlobType type, std::filesystem::path& path, std::vector<T>& v) {
    using namespace Common::FS;
    path.replace_extension(GetBlobFileExtension(type));
    if (EmulatorSettings.IsPipelineCacheArchived()) {
        int index{-1};
        index = mz_zip_reader_locate_file(&zip_ar, path.string().c_str(), nullptr, 0);
        if (index < 0) {
            LOG_WARNING(Render, "File {} is not found in the archive", path.string().c_str());
            return;
        }
        mz_zip_archive_file_stat stat{};
        mz_zip_reader_file_stat(&zip_ar, index, &stat);
        v.resize(stat.m_uncomp_size / sizeof(T));
        mz_zip_reader_extract_to_mem(&zip_ar, index, v.data(), stat.m_uncomp_size, 0);
    } else {
        // A missing profile.bin on first run or after driver migration is
        // normal. IOFile emits an error just for probing a missing file,
        // which misrepresents a safe cold cache as a cache corruption.
        // Leave v empty for CheckCacheProfile() to construct the REAL current
        // Shader::Profile; never stamp arbitrary old shader blobs as valid.
        if (type == BlobType::ShaderProfile) {
            std::error_code ec;
            const bool present = std::filesystem::exists(path, ec);
            if (!ec && !present) {
                return;
            }
        }
        const auto file = IOFile{path, FileAccessMode::Read};
        v.resize(file.GetSize() / sizeof(T));
        file.Read(v);
    }
}

bool DataBase::Save(BlobType type, const std::string& name, std::vector<u8>&& data) {
    if (!opened) {
        return false;
    }

    auto path = EmulatorSettings.IsPipelineCacheArchived() ? std::filesystem::path{name}
                                                           : cache_path / name;
    return WriteVector(type, std::move(path), std::move(data));
}

bool DataBase::Save(BlobType type, const std::string& name, std::vector<u32>&& data) {
    if (!opened) {
        return false;
    }

    auto path = EmulatorSettings.IsPipelineCacheArchived() ? std::filesystem::path{name}
                                                           : cache_path / name;
    return WriteVector(type, std::move(path), std::move(data));
}

void DataBase::Load(BlobType type, const std::string& name, std::vector<u8>& data) {
    if (!opened) {
        return;
    }

    auto path = EmulatorSettings.IsPipelineCacheArchived() ? std::filesystem::path{name}
                                                           : cache_path / name;
    return LoadVector(type, path, data);
}

void DataBase::Load(BlobType type, const std::string& name, std::vector<u32>& data) {
    if (!opened) {
        return;
    }

    auto path = EmulatorSettings.IsPipelineCacheArchived() ? std::filesystem::path{name}
                                                           : cache_path / name;
    return LoadVector(type, path, data);
}

size_t DataBase::CountBlobs(BlobType type) {
    const auto& ext = GetBlobFileExtension(type);
    size_t count = 0;
    if (EmulatorSettings.IsPipelineCacheArchived()) {
        const auto num_files = mz_zip_reader_get_num_files(&zip_ar);
        for (int index = 0; index < num_files; ++index) {
            std::array<char, MZ_ZIP_MAX_ARCHIVE_FILENAME_SIZE> file_name{};
            mz_zip_reader_get_filename(&zip_ar, index, file_name.data(), file_name.size());
            count += std::string{file_name.data()}.ends_with(ext);
        }
        return count;
    }
    std::error_code error;
    for (const auto& entry : std::filesystem::directory_iterator{cache_path, error}) {
        count += entry.path().extension().string().ends_with(ext);
    }
    return count;
}

std::vector<std::string> DataBase::ListMaliShaderBlobs() {
    std::vector<std::string> names;
    if (!IsOpened() || !ConcurrentReads()) return names;
    std::error_code ec;
    for (std::filesystem::directory_iterator it(cache_path, ec), end; !ec && it != end;
         it.increment(ec)) {
        if (it->path().extension() != ".spv") continue;
        const auto name = it->path().stem().string();
        if (name.size() > 32) continue;
        std::error_code entry_error;
        if (!it->is_regular_file(entry_error) || entry_error) continue;
        if (names.size() >= 65536) return {};
        names.push_back(name);
    }
    if (ec) return {};
    return names;
}

bool DataBase::ConcurrentReads() const {
    return !EmulatorSettings.IsPipelineCacheArchived();
}

void DataBase::ForEachBlob(BlobType type, const std::function<void(std::vector<u8>&& data)>& func,
                           const std::function<bool()>& stop) {
    const auto& ext = GetBlobFileExtension(type);
    if (EmulatorSettings.IsPipelineCacheArchived()) {
        const auto num_files = mz_zip_reader_get_num_files(&zip_ar);
        for (int index = 0; index < num_files; ++index) {
            std::array<char, MZ_ZIP_MAX_ARCHIVE_FILENAME_SIZE> file_name{};
            file_name.fill(0);
            mz_zip_reader_get_filename(&zip_ar, index, file_name.data(), file_name.size());
            if (std::string{file_name.data()}.ends_with(ext)) {
                mz_zip_archive_file_stat stat{};
                mz_zip_reader_file_stat(&zip_ar, index, &stat);
                std::vector<u8> data(stat.m_uncomp_size);
                mz_zip_reader_extract_to_mem(&zip_ar, index, data.data(), data.size(), 0);
                func(std::move(data));
            }
        }
    } else {
        for (const auto& file_name : std::filesystem::directory_iterator{cache_path}) {
            if (stop && stop()) {
                return;
            }
            if (file_name.path().extension().string().ends_with(ext)) {
                using namespace Common::FS;
                const auto& file = IOFile{file_name, FileAccessMode::Read};
                if (file.IsOpen()) {
                    std::vector<u8> data(file.GetSize());
                    file.Read(data);
                    func(std::move(data));
                }
            }
        }
    }
}

bool DataBase::ArchiveIncompatibleCache() {
    if (!opened || EmulatorSettings.IsPipelineCacheArchived()) {
        return false;
    }
    // Cache generations can differ when an app build changes Shader::Profile, a
    // PanVK option toggles or the serialized shader ABI is updated. Never erase
    // the previous generation: its shaders can still be useful to another build.
    // The cache IO worker has not yet been given work by CheckCacheProfile().
    std::error_code ec;
    std::filesystem::path archive;
    for (u32 attempt = 1; attempt <= 10000; ++attempt) {
        archive = cache_path / ("incompatible-" + std::to_string(attempt));
        if (!std::filesystem::exists(archive, ec)) {
            if (ec) {
                LOG_ERROR(Render, "Cannot inspect old shader-cache archive: {}", ec.message());
                return false;
            }
            break;
        }
        if (attempt == 10000) {
            LOG_ERROR(Render, "Shader-cache archive limit reached; refusing to delete cache");
            return false;
        }
    }
    if (!std::filesystem::create_directory(archive, ec)) {
        LOG_ERROR(Render, "Cannot preserve incompatible shader cache at {}: {}",
                  archive.string(), ec.message());
        return false;
    }
    u64 preserved = 0;
    for (const auto& entry : std::filesystem::directory_iterator{cache_path, ec}) {
        if (ec) {
            LOG_ERROR(Render, "Cannot enumerate incompatible shader cache: {}", ec.message());
            return false;
        }
        if (!entry.is_regular_file(ec) || entry.is_symlink(ec)) {
            if (ec) {
                LOG_ERROR(Render, "Cannot inspect shader cache file: {}", ec.message());
                return false;
            }
            continue;
        }
        const auto extension = entry.path().extension();
        const bool metadata = extension == ".spv" || extension == ".meta" ||
                              extension == ".key";
        const bool profile = entry.path().filename() == "profile.bin" ||
                             entry.path().filename() == "gow3-cache-schema.bin";
        if (!metadata && !profile) {
            continue; // Never move independent Vulkan driver cache or other user files.
        }
        std::filesystem::rename(entry.path(), archive / entry.path().filename(), ec);
        if (ec) {
            LOG_ERROR(Render, "Cannot archive incompatible shader cache file {}: {}",
                      entry.path().string(), ec.message());
            return false;
        }
        ++preserved;
    }
    if (ec) {
        LOG_ERROR(Render, "Cannot enumerate shader cache for preservation: {}", ec.message());
        return false;
    }
    LOG_WARNING(Render, "Incompatible shader cache preserved ({} files) in {}; rebuilding only "
                        "the active shader cache", preserved, archive.string());
    return true;
}

bool DataBase::RestoreCompatibleArchive(const std::vector<u8>& profile_bytes,
                                        const std::vector<u8>& schema_bytes) {
    if (!opened || EmulatorSettings.IsPipelineCacheArchived() || profile_bytes.empty()) {
        return false;
    }
    // A previous app/driver profile may become active again. Reuse its already
    // compiled shaders rather than forcing another on-demand compilation.
    const auto matches = [](const std::filesystem::path& path,
                            const std::vector<u8>& expected) {
        using namespace Common::FS;
        const auto file = IOFile{path, FileAccessMode::Read};
        if (!file.IsOpen() || file.GetSize() != expected.size()) {
            return false;
        }
        std::vector<u8> data(expected.size());
        file.Read(data);
        return data == expected;
    };
    // Shader::Profile has bool fields and may contain ABI padding. The active
    // cache uses field-wise operator==: requiring byte-identical padding here
    // would silently reject a still-compatible archived shader generation.
    // First validate size, then compare each real shader capability field.
    static_assert(std::is_trivially_copyable_v<Shader::Profile>);
    const auto matches_profile = [&](const std::filesystem::path& path) {
        if (profile_bytes.size() != sizeof(Shader::Profile)) {
            return false;
        }
        using namespace Common::FS;
        const auto file = IOFile{path, FileAccessMode::Read};
        if (!file.IsOpen() || file.GetSize() != sizeof(Shader::Profile)) {
            return false;
        }
        std::vector<u8> stored(sizeof(Shader::Profile));
        file.Read(stored);
        Shader::Profile previous{}, current{};
        std::memcpy(&previous, stored.data(), sizeof(previous));
        std::memcpy(&current, profile_bytes.data(), sizeof(current));
        return previous == current;
    };
    std::error_code ec;
    for (const auto& candidate : std::filesystem::directory_iterator{cache_path, ec}) {
        if (ec) {
            return false;
        }
        if (!candidate.is_directory(ec) ||
            !candidate.path().filename().string().starts_with("incompatible-")) {
            ec.clear();
            continue;
        }
        if (!matches_profile(candidate.path() / "profile.bin") ||
            (!schema_bytes.empty() &&
             !matches(candidate.path() / "gow3-cache-schema.bin", schema_bytes))) {
            continue;
        }
        // Restore the identity first. A partially restored generation after a
        // crash is still correctly marked, and warm-up reads only present blobs.
        auto restore_file = [&](const std::filesystem::path& file) {
            const auto dest = cache_path / file.filename();
            if (std::filesystem::exists(dest, ec) || ec) {
                return false;
            }
            std::filesystem::rename(file, dest, ec);
            return !ec;
        };
        if (!restore_file(candidate.path() / "profile.bin")) {
            LOG_ERROR(Render, "Cannot restore compatible shader profile from {}",
                      candidate.path().string());
            return false;
        }
        if (!schema_bytes.empty() &&
            !restore_file(candidate.path() / "gow3-cache-schema.bin")) {
            LOG_ERROR(Render, "Cannot restore compatible shader schema from {}",
                      candidate.path().string());
            return false;
        }
        u64 restored = 0;
        for (const auto& file : std::filesystem::directory_iterator{candidate.path(), ec}) {
            if (ec || !file.is_regular_file(ec) || file.is_symlink(ec)) {
                if (ec) return false;
                continue;
            }
            const auto ext = file.path().extension();
            if (ext != ".spv" && ext != ".meta" && ext != ".key") {
                continue;
            }
            if (!restore_file(file.path())) {
                LOG_ERROR(Render, "Cannot restore cached shader {}", file.path().string());
                return false;
            }
            ++restored;
        }
        std::filesystem::remove(candidate.path(), ec); // ignore unexpected non-cache files
        LOG_INFO(Render, "Restored {} shader-cache files from compatible generation",
                 restored);
        return true;
    }
    return false;
}

void DataBase::FinishPreload() {
    if (EmulatorSettings.IsPipelineCacheArchived()) {
        mz_zip_writer_init_from_reader(&zip_ar, cache_path.string().c_str());
        ar_is_read_only = false;
    }
}

} // namespace Storage
