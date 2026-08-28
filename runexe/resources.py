"""Parsing helpers for PE resources: the embedded application manifest
(RT_MANIFEST) and version info (RT_VERSION).

Both resource types live behind the same three-level resource directory
tree: Type -> Name -> Language -> Data. RunEXE only needs a single
manifest/version resource per executable, so the first Name and Language
entry found under a matching Type is used.
"""

import re
import struct

from .constants import RESOURCE_TYPE_MANIFEST, RESOURCE_TYPE_VERSION
from .models import PESection, VersionInfo
from .pe_utils import rva_range_to_file_offset, rva_to_file_offset

_EXECUTION_LEVEL_RE = re.compile(
    r"<(?:[\w.-]+:)?requestedExecutionLevel\b[^>]*\blevel\s*=\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)


def extract_requested_execution_level(manifest_xml: str) -> str | None:
    """Return the requestedExecutionLevel ('asInvoker',
    'requireAdministrator', 'highestAvailable', ...) declared in an
    embedded manifest, if any.

    Uses a regex rather than a full XML parser since embedded manifests
    can be malformed or use varying namespace prefixes; the goal here is
    a best-effort read, not strict validation.
    """

    match = _EXECUTION_LEVEL_RE.search(manifest_xml)
    return match.group(1) if match else None


# ---------------------------------------------------------------------
# Resource directory tree walking
# ---------------------------------------------------------------------


def _read_resource_directory_entries(
    file,
    directory_offset: int,
    allowed_start: int | None = None,
    allowed_end: int | None = None,
) -> list[tuple[int, int]] | None:
    """Read the entries of an IMAGE_RESOURCE_DIRECTORY at a file offset."""

    if (
        allowed_start is not None
        and allowed_end is not None
        and not (allowed_start <= directory_offset <= allowed_end - 16)
    ):
        return None

    file.seek(directory_offset)

    header = file.read(16)

    if len(header) != 16:
        return None

    (
        _characteristics,
        _timestamp,
        _major_version,
        _minor_version,
        number_of_named_entries,
        number_of_id_entries,
    ) = struct.unpack("<IIHHHH", header)

    total_entries = number_of_named_entries + number_of_id_entries

    # Safety limit against corrupt or hostile resource tables.
    if total_entries > 1024:
        return None

    if allowed_end is not None and directory_offset + 16 + total_entries * 8 > allowed_end:
        return None

    entries = []

    for _ in range(total_entries):
        entry_bytes = file.read(8)

        if len(entry_bytes) != 8:
            break

        name_or_id, offset_to_data = struct.unpack("<II", entry_bytes)
        entries.append((name_or_id, offset_to_data))

    return entries


def _find_resource_data(
    file,
    resource_base_offset: int,
    type_id: int,
    resource_size: int | None = None,
) -> tuple[int, int] | None:
    """Walk Type -> Name -> Language to find a resource's (RVA, size).

    Only numeric resource-type IDs are matched (named types are
    skipped). The top bit of an IMAGE_RESOURCE_DIRECTORY_ENTRY's
    OffsetToData marks it as pointing to a subdirectory rather than a
    leaf IMAGE_RESOURCE_DATA_ENTRY.
    """

    resource_end = resource_base_offset + resource_size if resource_size is not None else None
    type_entries = _read_resource_directory_entries(
        file, resource_base_offset, resource_base_offset, resource_end
    )

    if not type_entries:
        return None

    type_offset = None

    for name_or_id, offset_to_data in type_entries:
        if name_or_id == type_id:
            type_offset = offset_to_data
            break

    if type_offset is None or not (type_offset & 0x80000000):
        return None

    name_directory_offset = resource_base_offset + (type_offset & 0x7FFFFFFF)

    name_entries = _read_resource_directory_entries(
        file,
        name_directory_offset,
        resource_base_offset,
        resource_end,
    )

    if not name_entries:
        return None

    _, name_offset = name_entries[0]

    if not (name_offset & 0x80000000):
        return None

    language_directory_offset = resource_base_offset + (name_offset & 0x7FFFFFFF)

    language_entries = _read_resource_directory_entries(
        file,
        language_directory_offset,
        resource_base_offset,
        resource_end,
    )

    if not language_entries:
        return None

    _, language_offset = language_entries[0]

    if language_offset & 0x80000000:
        # Should be a leaf (data entry), not another subdirectory.
        return None

    data_entry_offset = resource_base_offset + language_offset

    if resource_end is not None and not (
        resource_base_offset <= data_entry_offset <= resource_end - 16
    ):
        return None

    file.seek(data_entry_offset)

    data_entry_bytes = file.read(16)

    if len(data_entry_bytes) != 16:
        return None

    data_rva, size, _code_page, _reserved = struct.unpack(
        "<IIII",
        data_entry_bytes,
    )

    return data_rva, size


def _read_resource_bytes(
    file,
    sections: list[PESection],
    resource_directory_rva: int,
    type_id: int,
    resource_directory_size: int | None = None,
    file_size: int | None = None,
) -> bytes | None:
    resource_base_offset = rva_to_file_offset(
        resource_directory_rva,
        sections,
    )

    if resource_base_offset is None:
        return None

    try:
        result = _find_resource_data(
            file,
            resource_base_offset,
            type_id,
            resource_directory_size,
        )
    except struct.error:
        return None

    if result is None:
        return None

    data_rva, size = result

    # Safety limit against corrupt size fields.
    if size <= 0 or size > 32 * 1024 * 1024:
        return None

    data_offset = rva_range_to_file_offset(data_rva, size, sections)

    if data_offset is None:
        return None

    if file_size is not None and (data_offset >= file_size or size > file_size - data_offset):
        return None

    file.seek(data_offset)

    data = file.read(size)

    if len(data) != size:
        return None

    return data


def extract_manifest(
    file,
    sections: list[PESection],
    resource_directory_rva: int,
    resource_directory_size: int | None = None,
    file_size: int | None = None,
) -> str | None:
    """Extract the embedded application manifest (RT_MANIFEST) as text."""

    data = _read_resource_bytes(
        file,
        sections,
        resource_directory_rva,
        RESOURCE_TYPE_MANIFEST,
        resource_directory_size,
        file_size,
    )

    if data is None:
        return None

    return _decode_manifest(data)


def _decode_manifest(data: bytes) -> str:
    """Decode common manifest encodings, including BOM-less UTF-16LE."""

    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace").rstrip("\x00")

    # Some linkers emit UTF-16LE XML without a byte-order mark.
    sample = data[:128]
    if sample and sample[1::2].count(0) > len(sample[1::2]) // 2:
        return data.decode("utf-16-le", errors="replace").rstrip("\x00")

    return data.decode("utf-8-sig", errors="replace").rstrip("\x00")


def extract_version_info(
    file,
    sections: list[PESection],
    resource_directory_rva: int,
    resource_directory_size: int | None = None,
    file_size: int | None = None,
) -> VersionInfo | None:
    """Extract the VS_VERSIONINFO resource (RT_VERSION), if present."""

    data = _read_resource_bytes(
        file,
        sections,
        resource_directory_rva,
        RESOURCE_TYPE_VERSION,
        resource_directory_size,
        file_size,
    )

    if data is None:
        return None

    try:
        return _parse_version_info(data)
    except (struct.error, IndexError):
        return None


# ---------------------------------------------------------------------
# VS_VERSIONINFO binary parsing
# ---------------------------------------------------------------------
#
# VS_VERSIONINFO, StringFileInfo, StringTable and String all share the
# same layout: a 3-word header (wLength, wValueLength, wType), a
# null-terminated UTF-16 key, padding to a 32-bit boundary, an optional
# value, more padding, then nested children. _iter_version_blocks()
# walks one level of that shared layout; the higher-level functions
# below use it recursively.


def _align4(offset: int) -> int:
    return (offset + 3) & ~3


def _read_wstring(raw: bytes, offset: int, limit: int | None = None) -> tuple[str, int]:
    """Decode a null-terminated UTF-16LE string starting at `offset`.

    Returns (string, offset immediately after the null terminator).
    """

    end = offset
    limit = min(limit if limit is not None else len(raw), len(raw))

    while end + 1 < limit and raw[end : end + 2] != b"\x00\x00":
        end += 2

    text = raw[offset:end].decode("utf-16-le", errors="replace")
    return text, min(end + 2, limit)


def _iter_version_blocks(raw: bytes, start: int, end: int):
    """Yield (key, value_words, value_offset, block_end) for each
    VERSIONINFO-style block found in raw[start:end]."""

    pos = start

    while pos + 6 <= end and pos + 6 <= len(raw):
        block_length = struct.unpack_from("<H", raw, pos)[0]

        if block_length == 0:
            break

        block_end = pos + block_length

        if block_end <= pos or block_end > end or block_end > len(raw):
            break

        value_words = struct.unpack_from("<H", raw, pos + 2)[0]
        key, key_end = _read_wstring(raw, pos + 6, block_end)
        value_offset = _align4(key_end)
        if value_offset > block_end:
            break

        yield key, value_words, value_offset, block_end

        pos = _align4(block_end)


def _parse_version_info(raw: bytes) -> VersionInfo:
    version_info = VersionInfo()

    if len(raw) < 6:
        return version_info

    w_length = struct.unpack_from("<H", raw, 0)[0]
    w_value_length = struct.unpack_from("<H", raw, 2)[0]
    w_type = struct.unpack_from("<H", raw, 4)[0]

    if w_length < 6 or w_length > len(raw):
        return version_info

    _key, key_end = _read_wstring(raw, 6, w_length)
    fixed_info_start = _align4(key_end)

    if w_value_length:
        # VS_FIXEDFILEINFO is a fixed 52-byte / 13-DWORD structure.
        fixed = raw[fixed_info_start : fixed_info_start + 52]

        if len(fixed) == 52:
            fields = struct.unpack("<13I", fixed)

            if fields[0] == 0xFEEF04BD:  # dwSignature
                file_version_ms, file_version_ls = fields[2], fields[3]
                product_version_ms, product_version_ls = fields[4], fields[5]

                version_info.file_version = (
                    f"{file_version_ms >> 16}.{file_version_ms & 0xFFFF}."
                    f"{file_version_ls >> 16}.{file_version_ls & 0xFFFF}"
                )
                version_info.product_version = (
                    f"{product_version_ms >> 16}."
                    f"{product_version_ms & 0xFFFF}."
                    f"{product_version_ls >> 16}."
                    f"{product_version_ls & 0xFFFF}"
                )

    # wValueLength is bytes for binary values (wType=0) and UTF-16 code
    # units for text values (wType=1). VS_FIXEDFILEINFO is binary.
    value_size = w_value_length if w_type == 0 else w_value_length * 2
    children_start = _align4(fixed_info_start + value_size)
    children_end = min(w_length, len(raw))

    for key, _value_words, value_offset, block_end in _iter_version_blocks(
        raw, children_start, children_end
    ):
        if key == "StringFileInfo":
            _parse_string_file_info(raw, value_offset, block_end, version_info)

    return version_info


def _parse_string_file_info(
    raw: bytes,
    start: int,
    end: int,
    version_info: VersionInfo,
) -> None:
    # Children here are StringTable blocks, one per language/codepage.
    for _table_key, _v, table_value_offset, table_end in _iter_version_blocks(raw, start, end):
        for name, value_words, value_offset, block_end in _iter_version_blocks(
            raw, table_value_offset, table_end
        ):
            if not value_words:
                continue

            value_end = min(value_offset + value_words * 2, block_end)
            value_bytes = raw[value_offset:value_end]

            version_info.strings[name] = value_bytes.decode(
                "utf-16-le",
                errors="replace",
            ).rstrip("\x00")
