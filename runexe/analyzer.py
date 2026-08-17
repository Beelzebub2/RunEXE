from dataclasses import dataclass
from pathlib import Path
import struct


@dataclass
class PEDataDirectory:
    virtual_address: int
    size: int


@dataclass
class PESection:
    name: str
    virtual_size: int
    virtual_address: int
    raw_size: int
    raw_offset: int


@dataclass
class ExecutableInfo:
    path: Path
    valid: bool
    format: str | None = None
    architecture: str | None = None
    reason: str | None = None
    sections: list[PESection] | None = None
    data_directories: list[PEDataDirectory] | None = None
    imports: list[PEImport] | None = None


@dataclass
class PEImport:
    name: str


MACHINE_TYPES = {
    0x014C: "x86",
    0x8664: "x86_64",
    0xAA64: "ARM64",
}


PE_FORMATS = {
    0x10B: "PE32 (32-bit)",
    0x20B: "PE32+ (64-bit)",
}


def rva_to_file_offset(
    rva: int,
    sections: list[PESection],
) -> int | None:
    """Convert a PE relative virtual address to a file offset."""

    for section in sections:
        section_start = section.virtual_address
        section_end = section_start + max(
            section.virtual_size,
            section.raw_size,
        )

        if section_start <= rva < section_end:
            offset_inside_section = rva - section_start
            return section.raw_offset + offset_inside_section

    return None


def parse_imports(
    file,
    import_rva: int,
    sections: list[PESection],
) -> list[PEImport]:
    """Parse the PE import directory and return imported DLLs."""

    import_offset = rva_to_file_offset(
        import_rva,
        sections,
    )

    if import_offset is None:
        return []

    imports = []

    descriptor_offset = import_offset

    while True:
        # Always return to the descriptor table before reading
        # the next descriptor.
        file.seek(descriptor_offset)

        descriptor = file.read(20)

        if len(descriptor) != 20:
            break

        (
            original_first_thunk,
            time_date_stamp,
            forwarder_chain,
            name_rva,
            first_thunk,
        ) = struct.unpack(
            "<IIIII",
            descriptor,
        )

        # A completely zeroed descriptor marks the end.
        if (
            original_first_thunk == 0
            and time_date_stamp == 0
            and forwarder_chain == 0
            and name_rva == 0
            and first_thunk == 0
        ):
            break

        name_offset = rva_to_file_offset(
            name_rva,
            sections,
        )

        if name_offset is not None:
            file.seek(name_offset)

            name_bytes = bytearray()

            # Put a safety limit on the string length.
            for _ in range(512):
                byte = file.read(1)

                if not byte or byte == b"\x00":
                    break

                name_bytes.extend(byte)

            if name_bytes:
                name = name_bytes.decode(
                    "ascii",
                    errors="replace",
                )

                imports.append(
                    PEImport(name=name)
                )

        # Move to the next IMAGE_IMPORT_DESCRIPTOR.
        descriptor_offset += 20

    return imports


def analyze_executable(file_path: str) -> ExecutableInfo:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not path.is_file():
        raise ValueError(f"Not a file: {path}")

    with path.open("rb") as file:

        # ---------------------------------------------------------
        # DOS HEADER
        # ---------------------------------------------------------

        mz_signature = file.read(2)

        if mz_signature != b"MZ":
            return ExecutableInfo(
                path=path,
                valid=False,
                reason=(
                    "Not a valid Windows executable "
                    "(missing MZ signature)"
                ),
            )

        # e_lfanew: file offset of the PE header
        file.seek(0x3C)

        pe_offset_bytes = file.read(4)

        if len(pe_offset_bytes) != 4:
            return ExecutableInfo(
                path=path,
                valid=False,
                reason=(
                    "File is too small to contain "
                    "a valid PE header"
                ),
            )

        pe_offset = struct.unpack(
            "<I",
            pe_offset_bytes,
        )[0]

        # ---------------------------------------------------------
        # PE SIGNATURE
        # ---------------------------------------------------------

        file.seek(pe_offset)

        pe_signature = file.read(4)

        if pe_signature != b"PE\x00\x00":
            return ExecutableInfo(
                path=path,
                valid=False,
                reason="Invalid PE signature",
            )

        # ---------------------------------------------------------
        # COFF HEADER
        # ---------------------------------------------------------

        # Machine
        machine_bytes = file.read(2)

        if len(machine_bytes) != 2:
            return ExecutableInfo(
                path=path,
                valid=False,
                reason="Missing machine type in PE header",
            )

        machine = struct.unpack(
            "<H",
            machine_bytes,
        )[0]

        architecture = MACHINE_TYPES.get(
            machine,
            f"Unknown (0x{machine:04X})",
        )

        # NumberOfSections
        number_of_sections_bytes = file.read(2)

        if len(number_of_sections_bytes) != 2:
            return ExecutableInfo(
                path=path,
                valid=False,
                reason="Missing number of sections in PE header",
            )

        number_of_sections = struct.unpack(
            "<H",
            number_of_sections_bytes,
        )[0]

        # TimeDateStamp
        # PointerToSymbolTable
        # NumberOfSymbols
        file.seek(12, 1)

        # SizeOfOptionalHeader
        optional_header_size_bytes = file.read(2)

        if len(optional_header_size_bytes) != 2:
            return ExecutableInfo(
                path=path,
                valid=False,
                reason="Missing optional header size",
            )

        optional_header_size = struct.unpack(
            "<H",
            optional_header_size_bytes,
        )[0]

        # Characteristics
        file.seek(2, 1)

        # ---------------------------------------------------------
        # OPTIONAL HEADER
        # ---------------------------------------------------------

        optional_header_start = file.tell()

        optional_header_magic_bytes = file.read(2)

        if len(optional_header_magic_bytes) != 2:
            return ExecutableInfo(
                path=path,
                valid=False,
                reason="Missing PE optional header",
            )

        optional_header_magic = struct.unpack(
            "<H",
            optional_header_magic_bytes,
        )[0]

        pe_format = PE_FORMATS.get(
            optional_header_magic,
            f"Unknown (0x{optional_header_magic:04X})",
        )

        if optional_header_magic == 0x10B:
            data_directory_offset = 96
        elif optional_header_magic == 0x20B:
            data_directory_offset = 112
        else:
            return ExecutableInfo(
                path=path,
                valid=False,
                reason="Unknown PE optional header format",
            )

        # ---------------------------------------------------------
        # DATA DIRECTORIES
        # ---------------------------------------------------------

        data_directory_start = (
            optional_header_start
            + data_directory_offset
        )

        file.seek(data_directory_start)

        data_directories = []

        for _ in range(16):
            directory_bytes = file.read(8)

            if len(directory_bytes) != 8:
                return ExecutableInfo(
                    path=path,
                    valid=False,
                    reason="Incomplete PE data directory",
                )

            virtual_address, size = struct.unpack(
                "<II",
                directory_bytes,
            )

            data_directories.append(
                PEDataDirectory(
                    virtual_address=virtual_address,
                    size=size,
                )
            )

        # ---------------------------------------------------------
        # SECTION TABLE
        # ---------------------------------------------------------

        section_table_start = (
            optional_header_start
            + optional_header_size
        )

        file.seek(section_table_start)

        sections = []

        for _ in range(number_of_sections):

            section_header = file.read(40)

            if len(section_header) != 40:
                return ExecutableInfo(
                    path=path,
                    valid=False,
                    reason="Incomplete PE section header",
                )

            name = section_header[0:8].rstrip(
                b"\x00"
            ).decode(
                "ascii",
                errors="replace",
            )

            virtual_size = struct.unpack(
                "<I",
                section_header[8:12],
            )[0]

            virtual_address = struct.unpack(
                "<I",
                section_header[12:16],
            )[0]

            raw_size = struct.unpack(
                "<I",
                section_header[16:20],
            )[0]

            raw_offset = struct.unpack(
                "<I",
                section_header[20:24],
            )[0]

            sections.append(
                PESection(
                    name=name,
                    virtual_size=virtual_size,
                    virtual_address=virtual_address,
                    raw_size=raw_size,
                    raw_offset=raw_offset,
                )
            )

        import_directory = data_directories[1]

        imports = []

        if (
            import_directory.virtual_address != 0
            and import_directory.size != 0
        ):
            imports = parse_imports(
                file,
                import_directory.virtual_address,
                sections,
            )

    return ExecutableInfo(
        path=path,
        valid=True,
        format=pe_format,
        architecture=architecture,
        sections=sections,
        data_directories=data_directories,
        imports=imports,
    )