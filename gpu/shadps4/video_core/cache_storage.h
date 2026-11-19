// SPDX-FileCopyrightText: Copyright 2025 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

#include "common/path_util.h"
#include "common/singleton.h"
#include "common/types.h"

#include <atomic>
#include <functional>
#include <thread>
#include <vector>

namespace Storage {

enum class BlobType : u32 {
    ShaderMeta,
    ShaderBinary,
    PipelineKey,
    ShaderProfile,
};

class DataBase {
public:
    static DataBase& Instance() {
        return *Common::Singleton<DataBase>::Instance();
    }

    void Open();
    void Close();
    [[nodiscard]] bool IsOpened() const {
        return opened.load(std::memory_order_acquire);
    }
    void FinishPreload();
    /// Keeps incompatible SPIR-V, pipeline keys and metadata for later recovery.
    /// Returns false if the old cache could not be preserved without data loss.
    [[nodiscard]] bool ArchiveIncompatibleCache();
    /// Reactivates a previously preserved generation with the same profile and schema.
    [[nodiscard]] bool RestoreCompatibleArchive(const std::vector<u8>& profile_bytes,
                                                const std::vector<u8>& schema_bytes);

    bool Save(BlobType type, const std::string& name, std::vector<u8>&& data);
    bool Save(BlobType type, const std::string& name, std::vector<u32>&& data);

    void Load(BlobType type, const std::string& name, std::vector<u8>& data);
    void Load(BlobType type, const std::string& name, std::vector<u32>& data);

    /// gow3: `stop` returning true ends the walk early (background warm-up at exit).
    void ForEachBlob(BlobType type, const std::function<void(std::vector<u8>&& data)>& func,
                     const std::function<bool()>& stop = {});
    /// gow3: blobs are plain files written beside and renamed into place, so other threads
    /// may read them while the IO thread saves (the zip archive cannot).
    [[nodiscard]] bool ConcurrentReads() const;
    /// gow3: number of blobs ForEachBlob visits (the loading screen's total).
    size_t CountBlobs(BlobType type);

private:
    std::jthread io_worker{};
    std::filesystem::path cache_path{};
    std::atomic_bool opened{};
};

} // namespace Storage
