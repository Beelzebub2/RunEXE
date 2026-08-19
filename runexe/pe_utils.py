from .models import PESection


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