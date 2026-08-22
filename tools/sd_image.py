#!/usr/bin/env python3
"""Deterministic PicoCalc SD RAW image packer and extractor.

The firmware backend intentionally models an SD card as a block device.  This
module is the host-side companion for the development loop: it turns a
directory tree into a deterministic FAT16/FAT32 RAW image and safely restores
that image to a directory tree.  It uses only the Python standard library and
does not call mkfs.fat, mcopy, or any other host utility.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import tempfile
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


SECTOR_SIZE = 512
FAT32_MIN_CLUSTERS = 65_525
FAT16_MIN_CLUSTERS = 4_085
FAT16_MAX_CLUSTERS = 65_524
MAX_FAT32_CLUSTERS = 2_000_000
MAX_DIRECTORY_DEPTH = 128
MAX_DIRECTORY_ENTRIES = 100_000
EOC32 = 0x0FFF_FFFF
EOC16 = 0xFFFF


class SdImageError(Exception):
    """An expected, user-correctable image or tree error."""


def _ceil_div(value: int, divisor: int) -> int:
    return (value + divisor - 1) // divisor


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _tree_sha256(entries: Sequence[Dict[str, object]]) -> str:
    return _sha256_bytes(_canonical_json(list(entries)))


def _path_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _reject_symlink_components(path: Path, description: str) -> Path:
    """Return an absolute path after rejecting every existing symlink component."""
    absolute = Path(os.path.abspath(path))
    components: List[Path] = []
    current = absolute
    while True:
        components.append(current)
        if current.parent == current:
            break
        current = current.parent
    for component in reversed(components):
        if component.is_symlink():
            raise SdImageError(f"{description} must not pass through a symlink: {component}")
    return absolute


_INVALID_NAME_CHARS = set('<>:"/\\|?*')
_RESERVED_DOS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _validate_component(name: str) -> None:
    if not name or name in (".", ".."):
        raise SdImageError(f"invalid FAT name: {name!r}")
    if "\x00" in name or any(ord(char) < 0x20 for char in name):
        raise SdImageError(f"FAT name contains a control character: {name!r}")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in name):
        raise SdImageError(f"FAT name contains an unpaired Unicode surrogate: {name!r}")
    if any(char in _INVALID_NAME_CHARS for char in name):
        raise SdImageError(f"FAT name contains an unsupported character: {name!r}")
    if name.endswith(" ") or name.endswith("."):
        raise SdImageError(f"FAT name may not end with space or dot: {name!r}")
    stem = name.split(".", 1)[0].upper()
    if stem in _RESERVED_DOS_NAMES:
        raise SdImageError(f"FAT reserved name is not allowed: {name!r}")
    try:
        utf16_units = len(name.encode("utf-16-le")) // 2
    except UnicodeError as error:
        raise SdImageError(f"FAT name is not valid UTF-16: {name!r}") from error
    if utf16_units > 255:
        raise SdImageError(f"FAT long name is longer than 255 UTF-16 code units: {name!r}")


def _name_key(name: str) -> Tuple[str, bytes]:
    return (name.casefold(), name.encode("utf-8", errors="surrogatepass"))


def _is_valid_short_char(char: str) -> bool:
    return char in "$%'-_@~`!(){}^#&" or (
        "A" <= char <= "Z" or "a" <= char <= "z" or "0" <= char <= "9"
    )


def _split_name(name: str) -> Tuple[str, str]:
    if name.startswith(".") and name.count(".") == 1:
        return name, ""
    if "." in name:
        return name.rsplit(".", 1)
    return name, ""


def _direct_short_name(name: str) -> Optional[bytes]:
    stem, extension = _split_name(name)
    if not (1 <= len(stem) <= 8 and len(extension) <= 3):
        return None
    if stem != stem.upper() or extension != extension.upper():
        return None
    if any(not _is_valid_short_char(char) for char in stem + extension):
        return None
    if stem in (".", "..") or stem.upper() in _RESERVED_DOS_NAMES:
        return None
    return (stem.ljust(8) + extension.ljust(3)).encode("ascii")


def _alias_stem(name: str) -> str:
    stem, _ = _split_name(name)
    value = "".join(char for char in stem.upper() if _is_valid_short_char(char))
    return value or "FILE"


def _alias_extension(name: str) -> str:
    _, extension = _split_name(name)
    return "".join(char for char in extension.upper() if _is_valid_short_char(char))[:3]


def _assign_aliases(children: Sequence["Node"]) -> None:
    used: Dict[bytes, str] = {}
    for child in children:
        direct = _direct_short_name(child.name)
        if direct is not None and direct not in used:
            child.short_name = direct
            used[direct] = child.name
    for child in children:
        if child.short_name is not None:
            continue
        stem = _alias_stem(child.name)
        extension = _alias_extension(child.name)
        number = 1
        while True:
            suffix = f"~{number}"
            candidate_stem = (stem[: max(1, 8 - len(suffix))] + suffix)[:8]
            candidate = (candidate_stem.ljust(8) + extension.ljust(3)).encode("ascii")
            if candidate not in used:
                child.short_name = candidate
                used[candidate] = child.name
                break
            number += 1
            if number > 999_999:
                raise SdImageError(f"could not generate a unique 8.3 alias for {child.name!r}")


@dataclass
class Node:
    name: str
    relative: str
    is_dir: bool
    source: Optional[Path] = None
    size: int = 0
    sha256: Optional[str] = None
    children: List["Node"] = field(default_factory=list)
    short_name: Optional[bytes] = None
    clusters: List[int] = field(default_factory=list)


def _scan_tree(root: Path) -> Node:
    root = _reject_symlink_components(Path(root), "input tree")
    if root.is_symlink() or not root.is_dir():
        raise SdImageError(f"input tree is not a real directory: {root}")
    root = root.resolve()

    def walk(directory: Path, relative: str, depth: int) -> Node:
        if depth > MAX_DIRECTORY_DEPTH:
            raise SdImageError("directory nesting exceeds the safety limit")
        node = Node(directory.name if relative else "", relative, True, directory)
        children: List[Node] = []
        seen: Dict[str, str] = {}
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: _name_key(entry.name))
        except OSError as error:
            raise SdImageError(f"cannot read directory {directory}: {error}") from error
        for entry in entries:
            _validate_component(entry.name)
            key = entry.name.casefold()
            if key in seen:
                raise SdImageError(
                    f"case-insensitive FAT name collision: {seen[key]!r} and {entry.name!r}"
                )
            seen[key] = entry.name
            child_relative = f"{relative}/{entry.name}" if relative else entry.name
            try:
                entry_stat = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise SdImageError(f"cannot stat {entry.path}: {error}") from error
            mode = entry_stat.st_mode
            if stat.S_ISLNK(mode):
                raise SdImageError(f"symlinks are not allowed in an SD tree: {child_relative}")
            if stat.S_ISDIR(mode):
                children.append(walk(Path(entry.path), child_relative, depth + 1))
            elif stat.S_ISREG(mode):
                child = Node(
                    entry.name,
                    child_relative,
                    False,
                    Path(entry.path),
                    entry_stat.st_size,
                    _sha256_file(Path(entry.path)),
                )
                children.append(child)
            else:
                raise SdImageError(f"only regular files and directories are allowed: {child_relative}")
        _assign_aliases(children)
        node.children = children
        return node

    result = walk(root, "", 0)
    if sum(1 for node in _walk_nodes(result)) - 1 > MAX_DIRECTORY_ENTRIES:
        raise SdImageError("input tree entry count exceeds the safety limit")
    return result


def _lfn_count(name: str) -> int:
    units = len(name.encode("utf-16-le")) // 2
    return _ceil_div(units + 1, 13)


def _needs_lfn(node: Node) -> bool:
    return _decode_short_name(node.short_name) != node.name


def _directory_entry_count(node: Node, is_root: bool) -> int:
    count = 0 if is_root else 2
    for child in node.children:
        count += (1 if _needs_lfn(child) else 0) * _lfn_count(child.name)
        count += 1
    return count


@dataclass(frozen=True)
class Geometry:
    fat_type: str
    total_sectors: int
    sectors_per_cluster: int
    reserved_sectors: int
    number_of_fats: int
    fat_sectors: int
    root_entries: int
    root_dir_sectors: int
    root_cluster: int

    @property
    def cluster_bytes(self) -> int:
        return self.sectors_per_cluster * SECTOR_SIZE

    @property
    def data_start(self) -> int:
        return self.reserved_sectors + self.number_of_fats * self.fat_sectors + self.root_dir_sectors

    @property
    def cluster_count(self) -> int:
        return (self.total_sectors - self.data_start) // self.sectors_per_cluster


def _fat_size(cluster_count: int, bytes_per_entry: int) -> int:
    return _ceil_div((cluster_count + 2) * bytes_per_entry, SECTOR_SIZE)


def _choose_geometry(total_sectors: int, fat_type: str) -> Geometry:
    if total_sectors <= 0:
        raise SdImageError("image size must be positive")
    if fat_type == "fat32":
        for sectors_per_cluster in (1, 2, 4, 8, 16, 32, 64, 128):
            fat_sectors = 1
            for _ in range(16):
                clusters = (total_sectors - 32 - 2 * fat_sectors) // sectors_per_cluster
                required = _fat_size(clusters, 4)
                if required <= fat_sectors:
                    break
                fat_sectors = required
            clusters = (total_sectors - 32 - 2 * fat_sectors) // sectors_per_cluster
            if FAT32_MIN_CLUSTERS <= clusters <= MAX_FAT32_CLUSTERS:
                return Geometry("fat32", total_sectors, sectors_per_cluster, 32, 2, fat_sectors, 0, 0, 2)
        raise SdImageError("image size cannot produce a bounded FAT32 geometry; increase --size-mib")
    if fat_type == "fat16":
        root_entries = 512
        root_dir_sectors = root_entries * 32 // SECTOR_SIZE
        # Keep FAT16 clusters at or below 32 KiB.  Larger clusters are legal
        # in some implementations but are not a safe default for embedded
        # FatFs profiles and make compatibility failures needlessly subtle.
        for sectors_per_cluster in (1, 2, 4, 8, 16, 32):
            fat_sectors = 1
            for _ in range(16):
                clusters = (
                    total_sectors - 1 - 2 * fat_sectors - root_dir_sectors
                ) // sectors_per_cluster
                required = _fat_size(clusters, 2)
                if required <= fat_sectors:
                    break
                fat_sectors = required
            clusters = (total_sectors - 1 - 2 * fat_sectors - root_dir_sectors) // sectors_per_cluster
            if FAT16_MIN_CLUSTERS <= clusters <= FAT16_MAX_CLUSTERS:
                return Geometry(
                    "fat16", total_sectors, sectors_per_cluster, 1, 2, fat_sectors,
                    root_entries, root_dir_sectors, 0,
                )
        raise SdImageError("image size cannot produce a FAT16 geometry; use FAT32 or adjust --size-mib")
    raise SdImageError(f"unsupported filesystem format: {fat_type}")


def _walk_nodes(root: Node) -> Iterable[Node]:
    yield root
    for child in root.children:
        yield from _walk_nodes(child)


def _assign_clusters(root: Node, geometry: Geometry) -> Dict[int, int]:
    fat: Dict[int, int] = {}
    next_cluster = 3 if geometry.fat_type == "fat32" else 2
    max_cluster = geometry.cluster_count + 1

    def allocate(count: int) -> List[int]:
        nonlocal next_cluster
        if count == 0:
            return []
        first = next_cluster
        last = first + count - 1
        if last > max_cluster:
            raise SdImageError("input tree does not fit in the selected RAW image size")
        clusters = list(range(first, last + 1))
        for index, cluster in enumerate(clusters):
            fat[cluster] = clusters[index + 1] if index + 1 < len(clusters) else (
                EOC32 if geometry.fat_type == "fat32" else EOC16
            )
        next_cluster = last + 1
        return clusters

    def allocate_directory(node: Node, is_root: bool, parent_cluster: int) -> None:
        entries = _directory_entry_count(node, is_root)
        count = max(1, _ceil_div(entries * 32, geometry.cluster_bytes))
        if is_root and geometry.fat_type == "fat32":
            node.clusters = [2] + allocate(count - 1)
            for index, cluster in enumerate(node.clusters):
                fat[cluster] = node.clusters[index + 1] if index + 1 < len(node.clusters) else EOC32
        elif is_root:
            node.clusters = []
        else:
            node.clusters = allocate(count)
        for child in node.children:
            if child.is_dir:
                allocate_directory(child, False, node.clusters[0] if node.clusters else parent_cluster)
            else:
                child.clusters = allocate(_ceil_div(child.size, geometry.cluster_bytes))

    if geometry.fat_type == "fat32":
        fat[0] = 0x0FFF_FFF8
        fat[1] = EOC32
    else:
        fat[0] = 0xFFF8
        fat[1] = EOC16
    allocate_directory(root, True, 0)
    return fat


def _fat_entry_bytes(cluster: int, value: int, fat_type: str) -> bytes:
    return struct.pack("<I" if fat_type == "fat32" else "<H", value)


def _short_checksum(short_name: bytes) -> int:
    checksum = 0
    for value in short_name:
        checksum = ((checksum & 1) << 7) + (checksum >> 1) + value
        checksum &= 0xFF
    return checksum


def _utf16_units(name: str) -> List[int]:
    encoded = name.encode("utf-16-le")
    return list(struct.unpack("<" + "H" * (len(encoded) // 2), encoded))


def _lfn_entries(name: str, short_name: bytes) -> List[bytes]:
    units = _utf16_units(name) + [0]
    units.extend([0xFFFF] * ((13 - len(units) % 13) % 13))
    count = len(units) // 13
    checksum = _short_checksum(short_name)
    result: List[bytes] = []
    for ordinal in range(count, 0, -1):
        chunk = units[(ordinal - 1) * 13 : ordinal * 13]
        entry = bytearray(32)
        entry[0] = ordinal | (0x40 if ordinal == count else 0)
        entry[11] = 0x0F
        entry[12] = 0
        entry[13] = checksum
        entry[26:28] = b"\x00\x00"
        for offset, unit in zip((1, 3, 5, 7, 9), chunk[:5]):
            entry[offset : offset + 2] = struct.pack("<H", unit)
        for offset, unit in zip((14, 16, 18, 20, 22, 24), chunk[5:11]):
            entry[offset : offset + 2] = struct.pack("<H", unit)
        for offset, unit in zip((28, 30), chunk[11:]):
            entry[offset : offset + 2] = struct.pack("<H", unit)
        result.append(bytes(entry))
    return result


def _short_entry(node: Node, first_cluster: int, geometry: Geometry, is_directory: bool) -> bytes:
    assert node.short_name is not None
    entry = bytearray(32)
    entry[0:11] = node.short_name
    entry[11] = 0x10 if is_directory else 0x20
    entry[20:22] = struct.pack("<H", (first_cluster >> 16) & 0xFFFF)
    entry[26:28] = struct.pack("<H", first_cluster & 0xFFFF)
    if not is_directory:
        entry[28:32] = struct.pack("<I", node.size)
    return bytes(entry)


def _directory_bytes(node: Node, geometry: Geometry, parent_cluster: int) -> bytes:
    entries: List[bytes] = []
    if node.relative:
        dot = Node(".", ".", True, short_name=b".          ")
        dotdot = Node("..", "..", True, short_name=b"..         ")
        entries.append(_short_entry(dot, node.clusters[0], geometry, True))
        entries.append(_short_entry(dotdot, parent_cluster if parent_cluster else 0, geometry, True))
    for child in node.children:
        assert child.short_name is not None
        if _needs_lfn(child):
            entries.extend(_lfn_entries(child.name, child.short_name))
        first_cluster = child.clusters[0] if child.clusters else 0
        entries.append(_short_entry(child, first_cluster, geometry, child.is_dir))
    entries.append(bytes(32))
    payload = b"".join(entries)
    capacity = (
        geometry.root_dir_sectors * SECTOR_SIZE
        if not node.relative and geometry.fat_type == "fat16"
        else max(1, len(node.clusters)) * geometry.cluster_bytes
    )
    if len(payload) > capacity:
        raise SdImageError(f"directory does not fit its allocated cluster chain: {node.relative or '/'}")
    return payload.ljust(capacity, b"\x00")


def _boot_sector(geometry: Geometry, volume_label: str) -> bytes:
    boot = bytearray(SECTOR_SIZE)
    boot[0:3] = b"\xEB\x58\x90" if geometry.fat_type == "fat32" else b"\xEB\x3C\x90"
    boot[3:11] = b"MSWIN4.1"
    boot[11:13] = struct.pack("<H", SECTOR_SIZE)
    boot[13] = geometry.sectors_per_cluster
    boot[14:16] = struct.pack("<H", geometry.reserved_sectors)
    boot[16] = geometry.number_of_fats
    boot[17:19] = struct.pack("<H", geometry.root_entries)
    boot[19:21] = struct.pack("<H", geometry.total_sectors if geometry.total_sectors < 0x10000 else 0)
    boot[21] = 0xF8
    boot[22:24] = struct.pack("<H", geometry.fat_sectors if geometry.fat_type == "fat16" else 0)
    boot[24:26] = struct.pack("<H", 63)
    boot[26:28] = struct.pack("<H", 255)
    boot[28:32] = struct.pack("<I", 0)
    boot[32:36] = struct.pack("<I", geometry.total_sectors if geometry.total_sectors >= 0x10000 else 0)
    if geometry.fat_type == "fat32":
        boot[36:40] = struct.pack("<I", geometry.fat_sectors)
        boot[40:42] = struct.pack("<H", 0)
        boot[42:44] = struct.pack("<H", 0)
        boot[44:48] = struct.pack("<I", geometry.root_cluster)
        boot[48:50] = struct.pack("<H", 1)
        boot[50:52] = struct.pack("<H", 6)
        boot[64] = 0x80
        boot[66] = 0x29
        boot[67:71] = struct.pack("<I", 0x1234_5678)
        boot[71:82] = volume_label.encode("ascii").ljust(11)
        boot[82:90] = b"FAT32   "
    else:
        boot[36] = 0x80
        boot[38] = 0x29
        boot[39:43] = struct.pack("<I", 0x1234_5678)
        boot[43:54] = volume_label.encode("ascii").ljust(11)
        boot[54:62] = b"FAT16   "
    boot[510:512] = b"\x55\xAA"
    return bytes(boot)


def _fsinfo_sector(geometry: Geometry, fat: Dict[int, int]) -> bytes:
    sector = bytearray(SECTOR_SIZE)
    allocated = sum(
        1 for cluster in range(2, geometry.cluster_count + 2) if cluster in fat
    )
    free = max(0, geometry.cluster_count - allocated)
    sector[0:4] = struct.pack("<I", 0x4161_5252)
    sector[484:488] = struct.pack("<I", 0x6141_7272)
    sector[488:492] = struct.pack("<I", free)
    sector[492:496] = struct.pack("<I", 3)
    sector[508:512] = struct.pack("<I", 0xAA55_0000)
    return bytes(sector)


def _node_manifest(root: Node) -> List[Dict[str, object]]:
    entries: List[Dict[str, object]] = []
    for node in _walk_nodes(root):
        if not node.relative:
            continue
        item: Dict[str, object] = {"path": node.relative, "type": "directory" if node.is_dir else "file"}
        if not node.is_dir:
            item["size"] = node.size
            item["sha256"] = node.sha256
        entries.append(item)
    return entries


def _write_at(stream, offset: int, data: bytes) -> None:
    stream.seek(offset)
    stream.write(data)


def _open_regular_source(path: Path):
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise SdImageError(f"cannot open input file safely: {path}: {error}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise SdImageError(f"input file is no longer a regular file: {path}")
        return os.fdopen(descriptor, "rb", closefd=True)
    except Exception:
        os.close(descriptor)
        raise


def _copy_file_to_image(stream, node: Node, geometry: Geometry) -> None:
    """Copy one file while checking the bytes against the scan snapshot."""
    assert node.source is not None
    expected_size = node.size
    expected_sha = node.sha256
    digest = hashlib.sha256()
    remaining = expected_size
    with _open_regular_source(node.source) as source:
        for cluster in node.clusters:
            want = min(geometry.cluster_bytes, remaining)
            data = source.read(want)
            if len(data) != want:
                raise SdImageError(f"input file changed while packing: {node.relative}")
            digest.update(data)
            remaining -= len(data)
            offset = (geometry.data_start + (cluster - 2) * geometry.sectors_per_cluster) * SECTOR_SIZE
            _write_at(stream, offset, data)
        if source.read(1):
            raise SdImageError(f"input file changed while packing: {node.relative}")
    if remaining != 0 or digest.hexdigest() != expected_sha:
        raise SdImageError(f"input file changed while packing: {node.relative}")


def pack_tree(input_dir: Path, output_image: Path, fat_type: str = "fat32", size_mib: int = 64, volume_label: str = "PICOCALC") -> Dict[str, object]:
    input_dir = _reject_symlink_components(Path(input_dir), "input tree")
    output_image = Path(output_image)
    output_image_for_check = _reject_symlink_components(output_image, "output image")
    output_image = output_image_for_check
    if _path_inside(output_image_for_check, input_dir):
        raise SdImageError("output image must not be inside the input tree")
    if output_image.exists():
        raise SdImageError(f"output image already exists (choose another path): {output_image}")
    output_image = output_image.absolute()
    if size_mib <= 0:
        raise SdImageError("--size-mib must be positive")
    volume_label = volume_label.upper()
    if not (1 <= len(volume_label) <= 11) or any(char not in " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!#$%&'()-@^_`{}~" for char in volume_label):
        raise SdImageError("volume label must be 1..11 uppercase ASCII FAT characters")
    root = _scan_tree(input_dir)
    initial_manifest = _node_manifest(root)
    geometry = _choose_geometry(size_mib * 2048, fat_type)
    fat = _assign_clusters(root, geometry)
    output_image.parent.mkdir(parents=True, exist_ok=True)
    temporary_fd, temporary_name = tempfile.mkstemp(
        prefix=output_image.name + ".tmp-", dir=output_image.parent
    )
    os.close(temporary_fd)
    temporary = Path(temporary_name)
    try:
        with temporary.open("w+b") as stream:
            stream.truncate(geometry.total_sectors * SECTOR_SIZE)
            _write_at(stream, 0, _boot_sector(geometry, volume_label))
            if geometry.fat_type == "fat32":
                _write_at(stream, SECTOR_SIZE, _fsinfo_sector(geometry, fat))
                _write_at(stream, 6 * SECTOR_SIZE, _boot_sector(geometry, volume_label))
                _write_at(stream, 7 * SECTOR_SIZE, _fsinfo_sector(geometry, fat))
            fat_start = geometry.reserved_sectors * SECTOR_SIZE
            entry_size = 4 if geometry.fat_type == "fat32" else 2
            for copy in range(geometry.number_of_fats):
                for cluster, value in fat.items():
                    _write_at(stream, fat_start + copy * geometry.fat_sectors * SECTOR_SIZE + cluster * entry_size, _fat_entry_bytes(cluster, value, geometry.fat_type))

            def write_node(node: Node, parent_cluster: int) -> None:
                if node.is_dir:
                    data = _directory_bytes(node, geometry, parent_cluster)
                    if not node.relative and geometry.fat_type == "fat16":
                        offset = (geometry.reserved_sectors + geometry.number_of_fats * geometry.fat_sectors) * SECTOR_SIZE
                        _write_at(stream, offset, data)
                    else:
                        for index, cluster in enumerate(node.clusters):
                            offset = (geometry.data_start + (cluster - 2) * geometry.sectors_per_cluster) * SECTOR_SIZE
                            start = index * geometry.cluster_bytes
                            _write_at(stream, offset, data[start : start + geometry.cluster_bytes])
                    for child in node.children:
                        write_node(child, node.clusters[0] if node.clusters else parent_cluster)
                else:
                    if not node.clusters:
                        _copy_file_to_image(stream, node, geometry)
                        return
                    _copy_file_to_image(stream, node, geometry)

            write_node(root, 0)
            stream.flush()
            os.fsync(stream.fileno())
        # The byte-copy loop detects changes to files that were present during
        # the initial scan.  A second complete scan also catches a file being
        # added, removed, renamed, or replaced by a directory while the image
        # was being built.  Do this before publishing the temporary image so
        # a failed snapshot never leaves a misleading output behind.
        final_manifest = _node_manifest(_scan_tree(input_dir))
        if final_manifest != initial_manifest:
            raise SdImageError("input tree changed while packing")
        os.replace(temporary, output_image)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    manifest = initial_manifest
    return {
        "operation": "pack",
        "format": fat_type,
        "image_bytes": geometry.total_sectors * SECTOR_SIZE,
        "sectors": geometry.total_sectors,
        "sectors_per_cluster": geometry.sectors_per_cluster,
        "tree_sha256": _tree_sha256(manifest),
        "image_sha256": _sha256_file(output_image),
        "files": manifest,
    }


class FatReader:
    def __init__(self, image: Path):
        self.image = _reject_symlink_components(Path(image), "input RAW image")
        try:
            self.stream = self.image.open("rb")
            self.size = self.image.stat().st_size
        except OSError as error:
            raise SdImageError(f"cannot open RAW image {image}: {error}") from error
        if self.size == 0 or self.size % SECTOR_SIZE:
            raise SdImageError("RAW image must be non-empty and a multiple of 512 bytes")
        self.total_sectors = self.size // SECTOR_SIZE
        boot = self._read_sector(0)
        if boot[11:13] != struct.pack("<H", SECTOR_SIZE) or boot[510:512] != b"\x55\xAA":
            raise SdImageError("RAW image has an invalid FAT boot sector")
        bpb_total_sectors = struct.unpack_from("<H", boot, 19)[0] or struct.unpack_from("<I", boot, 32)[0]
        if bpb_total_sectors != self.total_sectors:
            raise SdImageError("FAT BPB sector count does not match RAW image size")
        self.sectors_per_cluster = boot[13]
        self.reserved = struct.unpack_from("<H", boot, 14)[0]
        self.fats = boot[16]
        self.root_entries = struct.unpack_from("<H", boot, 17)[0]
        self.fat16_size = struct.unpack_from("<H", boot, 22)[0]
        self.fat32_size = struct.unpack_from("<I", boot, 36)[0] if self.root_entries == 0 else 0
        if (
            self.sectors_per_cluster == 0
            or self.sectors_per_cluster > 128
            or self.sectors_per_cluster & (self.sectors_per_cluster - 1)
            or self.reserved == 0
            or self.fats == 0
            or self.fats > 2
        ):
            raise SdImageError("FAT BPB has invalid cluster or FAT count")
        if self.root_entries == 0 and self.fat16_size == 0 and self.fat32_size:
            self.fat_type = "fat32"
            self.fat_sectors = self.fat32_size
            self.root_cluster = struct.unpack_from("<I", boot, 44)[0]
            self.root_dir_sectors = 0
        elif self.root_entries and self.fat16_size and self.fat32_size == 0:
            self.fat_type = "fat16"
            self.fat_sectors = self.fat16_size
            self.root_cluster = 0
            self.root_dir_sectors = _ceil_div(self.root_entries * 32, SECTOR_SIZE)
        else:
            raise SdImageError("FAT BPB does not identify a valid FAT16 or FAT32 layout")
        if self.fat_sectors == 0:
            raise SdImageError("FAT BPB has no FAT sectors")
        self.data_start = self.reserved + self.fats * self.fat_sectors + self.root_dir_sectors
        self.cluster_count = (self.total_sectors - self.data_start) // self.sectors_per_cluster
        if self.fat_type == "fat32" and self.cluster_count < FAT32_MIN_CLUSTERS:
            raise SdImageError("FAT32 image has too few clusters")
        if self.fat_type == "fat16" and not (FAT16_MIN_CLUSTERS <= self.cluster_count <= FAT16_MAX_CLUSTERS):
            raise SdImageError("FAT16 image has an invalid cluster count")
        if self.fat_type == "fat32" and self.cluster_count > MAX_FAT32_CLUSTERS:
            raise SdImageError("FAT32 image exceeds the safety cluster limit")
        if self.fat_type == "fat32" and not (2 <= self.root_cluster <= self.cluster_count + 1):
            raise SdImageError("FAT32 image has an invalid root cluster")
        self._validate_fat_copies()
        self._fat_cache: Dict[int, int] = {}

    def __del__(self) -> None:
        # Constructor validation can fail before a context manager is entered.
        # Close the stream in that path as well, so malformed images do not
        # leak a descriptor while the caller handles SdImageError.
        stream = getattr(self, "stream", None)
        if stream is not None and not stream.closed:
            stream.close()

    def __enter__(self) -> "FatReader":
        return self

    def __exit__(self, *_args: object) -> None:
        self.stream.close()

    @property
    def cluster_bytes(self) -> int:
        return self.sectors_per_cluster * SECTOR_SIZE

    def _read_sector(self, sector: int) -> bytes:
        if sector < 0 or sector >= self.total_sectors:
            raise SdImageError(f"sector out of range: {sector}")
        self.stream.seek(sector * SECTOR_SIZE)
        data = self.stream.read(SECTOR_SIZE)
        if len(data) != SECTOR_SIZE:
            raise SdImageError(f"truncated sector {sector}")
        return data

    def _validate_fat_copies(self) -> None:
        if self.fats < 1 or self.data_start > self.total_sectors:
            raise SdImageError("FAT BPB layout is outside the RAW image")
        if self.fats == 1:
            return
        fat_bytes = self.fat_sectors * SECTOR_SIZE
        first_offset = self.reserved * SECTOR_SIZE
        first = self._read_bytes(first_offset, fat_bytes)
        for copy in range(1, self.fats):
            current = self._read_bytes(first_offset + copy * fat_bytes, fat_bytes)
            if current != first:
                raise SdImageError("FAT copies are inconsistent")

    def _read_bytes(self, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0 or offset + length > self.size:
            raise SdImageError("RAW image read is outside the file")
        self.stream.seek(offset)
        data = self.stream.read(length)
        if len(data) != length:
            raise SdImageError("truncated RAW image data")
        return data

    def fat_entry(self, cluster: int) -> int:
        if cluster < 0 or cluster > self.cluster_count + 1:
            raise SdImageError(f"FAT entry cluster out of range: {cluster}")
        if cluster in self._fat_cache:
            return self._fat_cache[cluster]
        entry_size = 4 if self.fat_type == "fat32" else 2
        offset = self.reserved * SECTOR_SIZE + cluster * entry_size
        self.stream.seek(offset)
        data = self.stream.read(entry_size)
        if len(data) != entry_size:
            raise SdImageError(f"truncated FAT entry {cluster}")
        value = struct.unpack("<I" if entry_size == 4 else "<H", data)[0]
        if self.fat_type == "fat32":
            value &= 0x0FFF_FFFF
        self._fat_cache[cluster] = value
        return value

    def chain(self, first: int) -> List[int]:
        if first < 2 or first > self.cluster_count + 1:
            raise SdImageError(f"invalid FAT start cluster: {first}")
        chain: List[int] = []
        visited = set()
        current = first
        while True:
            if current in visited:
                raise SdImageError("FAT cluster chain contains a loop")
            if current < 2 or current > self.cluster_count + 1:
                raise SdImageError("FAT cluster chain points outside the image")
            visited.add(current)
            chain.append(current)
            value = self.fat_entry(current)
            if (self.fat_type == "fat32" and value >= 0x0FFF_FFF8) or (self.fat_type == "fat16" and value >= 0xFFF8):
                return chain
            if value in (0, 1) or (self.fat_type == "fat32" and 0x0FFF_FFF0 <= value <= 0x0FFF_FFF7) or (self.fat_type == "fat16" and 0xFFF0 <= value <= 0xFFF7):
                raise SdImageError("FAT cluster chain contains a free or bad entry")
            current = value

    def read_cluster(self, cluster: int) -> bytes:
        if cluster < 2 or cluster > self.cluster_count + 1:
            raise SdImageError(f"cluster out of range: {cluster}")
        first_sector = self.data_start + (cluster - 2) * self.sectors_per_cluster
        return b"".join(self._read_sector(first_sector + index) for index in range(self.sectors_per_cluster))

    def read_chain_bytes(self, chain: Sequence[int]) -> bytes:
        return b"".join(self.read_cluster(cluster) for cluster in chain)

    def read_directory_chain(self, chain: Sequence[int]) -> bytes:
        maximum = (MAX_DIRECTORY_ENTRIES + 2) * 32
        if len(chain) * self.cluster_bytes > maximum:
            raise SdImageError("directory allocation exceeds the safety limit")
        return self.read_chain_bytes(chain)

    def root_bytes(self) -> bytes:
        if self.fat_type == "fat32":
            return self.read_chain_bytes(self.chain(self.root_cluster))
        first_sector = self.reserved + self.fats * self.fat_sectors
        return b"".join(self._read_sector(first_sector + index) for index in range(self.root_dir_sectors))


def _decode_short_name(entry: bytes) -> str:
    stem = entry[0:8].decode("ascii", errors="strict").rstrip(" ")
    extension = entry[8:11].decode("ascii", errors="strict").rstrip(" ")
    return stem + (f".{extension}" if extension else "")


def _decode_lfn(pending: List[bytes], short_name: bytes) -> Optional[str]:
    if not pending:
        return None
    if any(entry[11] != 0x0F for entry in pending):
        raise SdImageError("invalid LFN attribute")
    sequences = [entry[0] & 0x1F for entry in pending]
    count = pending[0][0] & 0x1F
    if count == 0 or count > 20 or not (pending[0][0] & 0x40) or sorted(sequences) != list(range(1, count + 1)):
        raise SdImageError("invalid LFN sequence")
    checksum = pending[0][13]
    if any(entry[13] != checksum for entry in pending) or checksum != _short_checksum(short_name):
        raise SdImageError("LFN checksum mismatch")
    units: List[int] = []
    by_sequence = {entry[0] & 0x1F: entry for entry in pending}
    terminated = False
    for sequence in range(1, count + 1):
        entry = by_sequence[sequence]
        raw = entry[1:11] + entry[14:26] + entry[28:32]
        for index in range(0, len(raw), 2):
            unit = struct.unpack_from("<H", raw, index)[0]
            if unit == 0:
                terminated = True
                break
            if unit != 0xFFFF:
                units.append(unit)
        if terminated:
            break
    try:
        return bytes(struct.pack("<" + "H" * len(units), *units)).decode("utf-16-le")
    except (UnicodeError, struct.error) as error:
        raise SdImageError("invalid UTF-16 LFN") from error


def _parse_directory(reader: FatReader, data: bytes, parent: str) -> List[Tuple[str, bool, int, int]]:
    results: List[Tuple[str, bool, int, int]] = []
    pending: List[bytes] = []
    for offset in range(0, len(data), 32):
        entry = data[offset : offset + 32]
        if len(entry) != 32:
            break
        marker = entry[0]
        if marker == 0:
            break
        if marker == 0xE5:
            pending.clear()
            continue
        attr = entry[11]
        if attr == 0x0F:
            pending.append(entry)
            continue
        if attr & 0x08:
            pending.clear()
            continue
        if attr & 0xC0:
            raise SdImageError(f"unsupported FAT directory attribute in {parent or '/'}")
        short_name = entry[0:11]
        name = _decode_lfn(pending, short_name) if pending else _decode_short_name(entry)
        pending.clear()
        if name in (".", ".."):
            continue
        _validate_component(name)
        first_cluster = (struct.unpack_from("<H", entry, 20)[0] << 16) | struct.unpack_from("<H", entry, 26)[0]
        is_directory = bool(attr & 0x10)
        size = struct.unpack_from("<I", entry, 28)[0]
        results.append((name, is_directory, first_cluster, size))
        if len(results) > MAX_DIRECTORY_ENTRIES:
            raise SdImageError("directory entry count exceeds the safety limit")
    return results


def extract_tree(input_image: Path, output_dir: Path, force: bool = False) -> Dict[str, object]:
    input_image = _reject_symlink_components(Path(input_image), "input RAW image")
    output_dir = _reject_symlink_components(Path(output_dir), "output directory")
    if output_dir.exists():
        if not force:
            raise SdImageError(f"output directory exists (use --force only for an empty directory): {output_dir}")
        if output_dir.is_symlink() or not output_dir.is_dir() or any(output_dir.iterdir()):
            raise SdImageError("--force requires an existing empty real directory")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output_dir.name + ".tmp-", dir=output_dir.parent))
    try:
        with FatReader(input_image) as reader:
            manifest: List[Dict[str, object]] = []
            seen_paths: set = set()
            used_clusters: Dict[int, str] = {}

            def claim_clusters(chain: Sequence[int], path: str) -> None:
                for cluster in chain:
                    previous = used_clusters.get(cluster)
                    if previous is not None:
                        raise SdImageError(
                            f"FAT cluster {cluster} is shared by {previous} and {path}"
                        )
                    used_clusters[cluster] = path

            root_chain: Optional[List[int]] = None
            if reader.fat_type == "fat32":
                root_chain = reader.chain(reader.root_cluster)
                claim_clusters(root_chain, "/")

            def restore_directory(data: bytes, destination: Path, relative: str, depth: int) -> None:
                if depth > MAX_DIRECTORY_DEPTH:
                    raise SdImageError("directory nesting exceeds the safety limit")
                children = _parse_directory(reader, data, relative)
                names: Dict[str, str] = {}
                for name, is_directory, first_cluster, size in children:
                    key = name.casefold()
                    if key in names:
                        raise SdImageError(f"case-insensitive FAT name collision in {relative or '/'}")
                    names[key] = name
                    child_relative = f"{relative}/{name}" if relative else name
                    if child_relative in seen_paths:
                        raise SdImageError(f"duplicate FAT path: {child_relative}")
                    seen_paths.add(child_relative)
                    if len(seen_paths) > MAX_DIRECTORY_ENTRIES:
                        raise SdImageError("FAT tree entry count exceeds the safety limit")
                    target = destination / name
                    if is_directory:
                        if first_cluster == 0:
                            raise SdImageError(f"directory has no cluster: {child_relative}")
                        target.mkdir()
                        chain = reader.chain(first_cluster)
                        claim_clusters(chain, child_relative)
                        restore_directory(reader.read_directory_chain(chain), target, child_relative, depth + 1)
                        manifest.append({"path": child_relative, "type": "directory"})
                    else:
                        if size == 0:
                            if first_cluster != 0:
                                raise SdImageError(f"empty file has a cluster: {child_relative}")
                            file_sha = hashlib.sha256(b"").hexdigest()
                        else:
                            if first_cluster == 0:
                                raise SdImageError(f"non-empty file has no cluster: {child_relative}")
                            chain = reader.chain(first_cluster)
                            needed = _ceil_div(size, reader.cluster_bytes)
                            if len(chain) != needed:
                                raise SdImageError(f"file cluster chain length does not match its size: {child_relative}")
                            claim_clusters(chain, child_relative)
                        temporary_file = target.with_name(target.name + ".tmp")
                        with temporary_file.open("wb") as stream:
                            digest = hashlib.sha256()
                            remaining = size
                            if size:
                                for cluster in chain:
                                    data = reader.read_cluster(cluster)
                                    chunk = data[:remaining]
                                    if not chunk:
                                        raise SdImageError(f"file cluster chain is shorter than its size: {child_relative}")
                                    stream.write(chunk)
                                    digest.update(chunk)
                                    remaining -= len(chunk)
                                if remaining != 0:
                                    raise SdImageError(f"file cluster chain is shorter than its size: {child_relative}")
                            file_sha = digest.hexdigest()
                            stream.flush()
                            os.fsync(stream.fileno())
                        os.replace(temporary_file, target)
                        manifest.append({"path": child_relative, "type": "file", "size": size, "sha256": file_sha})

            root_data = (
                reader.read_directory_chain(root_chain)
                if root_chain is not None
                else reader.root_bytes()
            )
            restore_directory(root_data, temporary, "", 0)
            manifest.sort(key=lambda item: _name_key(str(item["path"])))
            tree_sha = _tree_sha256(manifest)
            fat_type = reader.fat_type
        if output_dir.exists():
            output_dir.rmdir()
        os.replace(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "operation": "extract",
        "format": fat_type,
        "image_bytes": input_image.stat().st_size,
        "image_sha256": _sha256_file(input_image),
        "tree_sha256": tree_sha,
        "files": manifest,
    }


def _write_report(report: Dict[str, object], path: Optional[Path]) -> None:
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path is None:
        print(text, end="")
        return
    path = _reject_symlink_components(Path(path), "JSON report")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".tmp-", dir=path.parent)
    os.close(temporary_fd)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def add_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("sd", help="pack/extract deterministic SD RAW images")
    commands = parser.add_subparsers(dest="sd_command", required=True)
    pack = commands.add_parser("pack", help="pack a directory tree into a FAT RAW image")
    pack.add_argument("input_dir", type=Path)
    pack.add_argument("output_image", type=Path)
    pack.add_argument("--format", choices=("fat32", "fat16"), default="fat32")
    pack.add_argument("--size-mib", type=int, default=64, help="RAW image size in MiB (default: 64)")
    pack.add_argument("--volume-label", default="PICOCALC")
    pack.add_argument("--json", dest="json_path", type=Path, help="write a machine-readable report")
    extract = commands.add_parser("extract", help="extract a FAT RAW image into a directory tree")
    extract.add_argument("input_image", type=Path)
    extract.add_argument("output_dir", type=Path)
    extract.add_argument("--force", action="store_true", help="allow an existing empty output directory")
    extract.add_argument("--json", dest="json_path", type=Path, help="write a machine-readable report")


def run_cli(args: argparse.Namespace) -> int:
    try:
        if args.sd_command == "pack":
            report = pack_tree(args.input_dir, args.output_image, args.format, args.size_mib, args.volume_label.upper())
        elif args.sd_command == "extract":
            report = extract_tree(args.input_image, args.output_dir, args.force)
        else:
            raise SdImageError("an SD subcommand is required")
        _write_report(report, args.json_path)
        return 0
    except (SdImageError, OSError, UnicodeError) as error:
        print(f"error: {error}", file=os.sys.stderr)
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(prog="picocalc-sd")
    commands = parser.add_subparsers(dest="command", required=True)
    add_cli(commands)
    args = parser.parse_args()
    return run_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
