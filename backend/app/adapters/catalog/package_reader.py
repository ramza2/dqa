"""Safe in-memory Catalog Package ZIP reader (no filesystem extraction)."""

from __future__ import annotations

import hashlib
import io
import posixpath
import zipfile
from dataclasses import dataclass, field

from app.adapters.catalog.errors import CatalogPackageErrorCode, CatalogPackageValidationError
from app.adapters.catalog.limits import (
    DEFAULT_ZIP_LIMITS,
    MANIFEST_FILENAME,
    PACKAGE_ROOT_NAME,
    CatalogPackageZipLimits,
)

# Unix file type bits in ZipInfo.external_attr (high 16 bits).
_S_IFMT = 0o170000
_S_IFREG = 0o100000
_S_IFDIR = 0o040000
_S_IFLNK = 0o120000


@dataclass(frozen=True)
class PackageFileEntry:
    """One regular file under the package root."""

    relative_path: str
    data: bytes
    sha256: str

    @property
    def size(self) -> int:
        return len(self.data)


@dataclass
class SafePackageArchive:
    """ZIP contents after path/size/type safety checks (still pre-manifest)."""

    archive_sha256: str
    archive_size: int
    files: dict[str, PackageFileEntry] = field(default_factory=dict)
    directory_paths: frozenset[str] = field(default_factory=frozenset)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_safe_package_archive(
    archive_bytes: bytes,
    *,
    limits: CatalogPackageZipLimits = DEFAULT_ZIP_LIMITS,
) -> SafePackageArchive:
    """Inspect and load a Catalog Package ZIP entirely in memory.

    Never extracts to the filesystem. Rejects traversal, duplicates, symlinks,
    expansion bombs, and entries outside the single expected package root.
    """
    if not archive_bytes:
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.EMPTY_UPLOAD,
            "uploaded archive is empty",
        )
    if len(archive_bytes) > limits.max_archive_bytes:
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.ARCHIVE_TOO_LARGE,
            "archive exceeds maximum allowed compressed size",
        )

    archive_digest = sha256_hex(archive_bytes)

    try:
        zf = zipfile.ZipFile(io.BytesIO(archive_bytes), mode="r")
    except zipfile.BadZipFile as exc:
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.INVALID_ZIP,
            "uploaded file is not a readable ZIP archive",
        ) from exc

    with zf:
        infos = list(zf.infolist())
        if len(infos) > limits.max_entry_count:
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.TOO_MANY_ENTRIES,
                "archive contains too many entries",
            )

        _reject_duplicate_raw_names(infos)
        _reject_expansion_limits(infos, limits)

        files: dict[str, PackageFileEntry] = {}
        directories: set[str] = set()
        normalized_seen: set[str] = set()

        for info in infos:
            kind, relative = _classify_entry(info.filename)
            if relative in normalized_seen:
                raise CatalogPackageValidationError(
                    CatalogPackageErrorCode.DUPLICATE_ENTRY,
                    "duplicate normalized package path",
                    path=relative or info.filename,
                )
            normalized_seen.add(relative)

            if kind == "root_dir":
                directories.add("")
                continue

            _reject_non_regular(info, path=relative)

            if kind == "directory":
                directories.add(relative)
                continue

            # Regular file
            if info.file_size > limits.max_uncompressed_file_bytes:
                raise CatalogPackageValidationError(
                    CatalogPackageErrorCode.UNCOMPRESSED_TOO_LARGE,
                    "file exceeds maximum uncompressed size",
                    path=relative,
                )

            try:
                data = zf.read(info)
            except Exception as exc:  # noqa: BLE001 - zip decoding failures
                raise CatalogPackageValidationError(
                    CatalogPackageErrorCode.INVALID_ZIP,
                    "failed to read ZIP entry",
                    path=relative,
                ) from exc

            if len(data) != info.file_size:
                raise CatalogPackageValidationError(
                    CatalogPackageErrorCode.INVALID_ZIP,
                    "ZIP entry size does not match declared uncompressed size",
                    path=relative,
                )
            if len(data) > limits.max_uncompressed_file_bytes:
                raise CatalogPackageValidationError(
                    CatalogPackageErrorCode.UNCOMPRESSED_TOO_LARGE,
                    "file exceeds maximum uncompressed size",
                    path=relative,
                )

            files[relative] = PackageFileEntry(
                relative_path=relative,
                data=data,
                sha256=sha256_hex(data),
            )

        if MANIFEST_FILENAME not in files:
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.MISSING_MANIFEST,
                "manifest.json is missing from package root",
                path=MANIFEST_FILENAME,
            )

        return SafePackageArchive(
            archive_sha256=archive_digest,
            archive_size=len(archive_bytes),
            files=files,
            directory_paths=frozenset(directories),
        )


def _reject_duplicate_raw_names(infos: list[zipfile.ZipInfo]) -> None:
    seen: set[str] = set()
    for info in infos:
        name = info.filename
        if name in seen:
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.DUPLICATE_ENTRY,
                "duplicate ZIP entry name",
                path=name,
            )
        seen.add(name)


def _reject_expansion_limits(
    infos: list[zipfile.ZipInfo],
    limits: CatalogPackageZipLimits,
) -> None:
    total_uncompressed = 0
    for info in infos:
        if info.is_dir():
            continue
        total_uncompressed += max(0, int(info.file_size))
        if total_uncompressed > limits.max_uncompressed_total_bytes:
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.UNCOMPRESSED_TOO_LARGE,
                "archive exceeds maximum total uncompressed size",
            )
        compressed = int(info.compress_size)
        uncompressed = int(info.file_size)
        if compressed > 0 and uncompressed > 0:
            ratio = uncompressed / compressed
            if ratio > limits.max_compression_ratio:
                raise CatalogPackageValidationError(
                    CatalogPackageErrorCode.COMPRESSION_RATIO,
                    "ZIP entry compression ratio exceeds allowed maximum",
                    path=info.filename,
                )


def _classify_entry(raw_name: str) -> tuple[str, str]:
    """Return (kind, relative_path) where kind is root_dir|directory|file."""
    if not raw_name or raw_name.endswith("\x00") or "\x00" in raw_name:
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.UNSAFE_PATH,
            "ZIP entry path is unsafe",
            path=raw_name or None,
        )

    # Reject Windows separators / drive letters before normalization.
    if "\\" in raw_name:
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.UNSAFE_PATH,
            "ZIP entry path contains backslash",
            path=raw_name,
        )
    if raw_name.startswith("/"):
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.UNSAFE_PATH,
            "ZIP entry path is absolute",
            path=raw_name,
        )
    if len(raw_name) >= 2 and raw_name[1] == ":" and raw_name[0].isalpha():
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.UNSAFE_PATH,
            "ZIP entry path looks like a Windows drive path",
            path=raw_name,
        )

    raw_parts = [p for p in raw_name.split("/") if p != ""]
    if any(part == ".." for part in raw_parts):
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.UNSAFE_PATH,
            "ZIP entry path contains parent traversal",
            path=raw_name,
        )

    # Normalize to posix; reject empty / traversal components.
    collapsed = posixpath.normpath(raw_name)
    if collapsed in (".", ""):
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.UNSAFE_PATH,
            "ZIP entry path is unsafe",
            path=raw_name,
        )
    if collapsed.startswith("../") or collapsed == ".." or "/../" in f"/{collapsed}/":
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.UNSAFE_PATH,
            "ZIP entry path contains parent traversal",
            path=raw_name,
        )
    if collapsed.startswith("/"):
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.UNSAFE_PATH,
            "ZIP entry path is absolute",
            path=raw_name,
        )

    parts = [p for p in collapsed.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.UNSAFE_PATH,
            "ZIP entry path contains parent traversal",
            path=raw_name,
        )
    if not parts or parts[0] != PACKAGE_ROOT_NAME:
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.INVALID_ROOT,
            f"ZIP entry is outside the required '{PACKAGE_ROOT_NAME}/' root",
            path=raw_name,
        )

    is_directory = raw_name.endswith("/") or collapsed.endswith("/")
    relative_parts = parts[1:]
    relative = "/".join(relative_parts)

    if not relative_parts:
        if is_directory or raw_name.rstrip("/").endswith(PACKAGE_ROOT_NAME):
            return "root_dir", ""
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.INVALID_ROOT,
            "package root must be a directory entry or contain nested files",
            path=raw_name,
        )

    if is_directory:
        return "directory", relative
    return "file", relative


def _reject_non_regular(info: zipfile.ZipInfo, *, path: str) -> None:
    """Reject symlinks and other non-regular file types."""
    # Explicit symlink create system markers / mode bits.
    mode = (info.external_attr >> 16) & 0xFFFF
    file_type = mode & _S_IFMT
    if file_type == _S_IFLNK:
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.NON_REGULAR_ENTRY,
            "symbolic link entries are not allowed",
            path=path,
        )
    if file_type and file_type not in (_S_IFREG, _S_IFDIR) and not info.is_dir():
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.NON_REGULAR_ENTRY,
            "non-regular ZIP entries are not allowed",
            path=path,
        )

    # Some producers set MS-DOS directory attribute without Unix mode.
    if info.is_dir():
        return

    # Reject entries that claim to be directories via attribute but lack trailing slash
    # only when DOS directory bit is set without being a file read target — handled
    # via is_dir() above. Extra guard: Unix socket/device types already covered.
