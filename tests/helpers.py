import struct
from pathlib import Path


def make_pe(
    path: Path,
    *,
    machine: int = 0x014C,
    subsystem: int = 3,
    with_import: bool = True,
    original_first_thunk: bool = True,
) -> Path:
    """Create a small, structurally valid PE32 fixture."""

    pe_offset = 0x80
    optional_size = 224
    raw_offset = 0x200
    image = bytearray(0x400)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, pe_offset)
    image[pe_offset : pe_offset + 4] = b"PE\0\0"
    struct.pack_into(
        "<HHIIIHH",
        image,
        pe_offset + 4,
        machine,
        1,
        0,
        0,
        0,
        optional_size,
        0x0102,
    )

    optional = pe_offset + 24
    struct.pack_into("<H", image, optional, 0x10B)
    struct.pack_into("<H", image, optional + 68, subsystem)
    struct.pack_into("<I", image, optional + 92, 16)
    if with_import:
        struct.pack_into("<II", image, optional + 96 + 8, 0x1000, 40)

    section = optional + optional_size
    image[section : section + 8] = b".rdata\0\0"
    struct.pack_into("<IIII", image, section + 8, 0x200, 0x1000, 0x200, raw_offset)

    if with_import:
        lookup_rva = 0x1050
        original_rva = lookup_rva if original_first_thunk else 0
        struct.pack_into("<IIIII", image, raw_offset, original_rva, 0, 0, 0x1040, lookup_rva)
        image[raw_offset + 0x40 : raw_offset + 0x4D] = b"KERNEL32.dll\0"
        struct.pack_into("<II", image, raw_offset + 0x50, 0x1060, 0)
        struct.pack_into("<H", image, raw_offset + 0x60, 0)
        image[raw_offset + 0x62 : raw_offset + 0x6E] = b"ExitProcess\0"

    path.write_bytes(image)
    return path


def version_block(
    key: str,
    *,
    value: bytes = b"",
    value_length: int = 0,
    value_type: int = 1,
    children: bytes = b"",
) -> bytes:
    key_bytes = (key + "\0").encode("utf-16-le")
    body = bytearray(struct.pack("<HHH", 0, value_length, value_type) + key_bytes)
    body.extend(b"\0" * ((-len(body)) % 4))
    body.extend(value)
    body.extend(b"\0" * ((-len(body)) % 4))
    body.extend(children)
    struct.pack_into("<H", body, 0, len(body))
    return bytes(body)


def make_version_info() -> bytes:
    product_value = "RunEXE\0".encode("utf-16-le")
    product = version_block(
        "ProductName",
        value=product_value,
        value_length=len("RunEXE\0"),
        value_type=1,
    )
    table = version_block("040904B0", children=product)
    strings = version_block("StringFileInfo", children=table)
    fixed = struct.pack(
        "<13I",
        0xFEEF04BD,
        0x00010000,
        1 << 16 | 2,
        3 << 16 | 4,
        5 << 16 | 6,
        7 << 16 | 8,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    return version_block(
        "VS_VERSION_INFO",
        value=fixed,
        value_length=len(fixed),
        value_type=0,
        children=strings,
    )
