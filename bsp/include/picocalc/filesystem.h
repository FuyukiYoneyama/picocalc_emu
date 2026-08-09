#pragma once

#include <stddef.h>
#include <stdint.h>

namespace picocalc::filesystem {

enum class Error : uint8_t {
    Ok = 0,
    InvalidArgument,
    NotMounted,
    Busy,
    MountFailed,
    OpenFailed,
    ReadFailed,
    SeekFailed,
    CloseFailed,
    DirectoryFailed,
    EndOfDirectory,
    NotFound,
    WriteFailed,
    SyncFailed,
    RemoveFailed,
    RenameFailed,
};

const char* error_name(Error error);

// The handles are intentionally opaque. The implementation owns the single
// FATFS/FIL and fixed directory-frame pool, so application code never includes ff.h.
struct FileHandle {
    uint32_t token = 0;
};

struct DirectoryHandle {
    uint32_t token = 0;
};

struct ReadResult {
    size_t bytes = 0;
    Error error = Error::Ok;

    bool ok() const {
        return error == Error::Ok;
    }
};

struct DirectoryEntry {
    char name[128]{};
    uint32_t size = 0;
    bool is_dir = false;
};

struct FileInfo {
    uint32_t size = 0;
    bool is_dir = false;
};

struct WriteResult {
    size_t bytes = 0;
    Error error = Error::Ok;

    bool ok() const {
        return error == Error::Ok;
    }
};

Error mount();
Error unmount();
bool mounted();

// The BSP owns one file object. A file and directory enumeration cannot be
// active together; operations that would conflict return Busy.
Error open_read(const char* path, FileHandle* handle);
Error stat(const char* path, FileInfo* info);
Error open_write_truncate(const char* path, FileHandle* handle);
ReadResult read(FileHandle* handle, void* destination, size_t bytes);
WriteResult write(FileHandle* handle, const void* source, size_t bytes);
Error seek(FileHandle* handle, uint32_t offset);
Error tell(const FileHandle* handle, uint32_t* offset);
Error size(const FileHandle* handle, uint32_t* bytes);
Error close(FileHandle* handle);
Error sync(FileHandle* handle);

Error open_dir(const char* path, DirectoryHandle* handle);
Error next_dir(DirectoryHandle* handle, DirectoryEntry* entry);
Error close_dir(DirectoryHandle* handle);

Error remove(const char* path);
Error rename(const char* from, const char* to);

enum class SmokeStage : uint8_t {
    Ok = 0,
    Mount,
    OpenWrite,
    Write,
    Sync,
    CloseWrite,
    OpenRead,
    Read,
    Compare,
    CloseRead,
    Remove,
};

struct SmokeResult {
    SmokeStage stage;
    uint32_t detail;

    bool ok() const {
        return stage == SmokeStage::Ok;
    }
};

SmokeResult smoke_test(const char* path = "0:/PICOTEST.TXT");
const char* stage_name(SmokeStage stage);

}  // namespace picocalc::filesystem
