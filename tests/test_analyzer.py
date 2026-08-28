import struct

from runexe.analyzer import analyze_executable
from runexe.models import PESection
from runexe.pe_utils import rva_range_to_file_offset, rva_to_file_offset

from .helpers import make_pe


def test_analyzes_minimal_pe_and_imports(tmp_path):
    path = make_pe(tmp_path / "sample.exe")

    result = analyze_executable(path)

    assert result.valid
    assert result.architecture == "x86"
    assert result.format == "PE32 (32-bit)"
    assert result.subsystem == "Windows Console"
    assert result.imports[0].name == "KERNEL32.dll"
    assert result.imports[0].functions == ["ExitProcess"]


def test_uses_first_thunk_when_original_thunk_is_absent(tmp_path):
    result = analyze_executable(make_pe(tmp_path / "bound.exe", original_first_thunk=False))

    assert result.valid
    assert result.imports[0].functions == ["ExitProcess"]


def test_rejects_pe_header_offset_outside_file(tmp_path):
    path = tmp_path / "bad.exe"
    raw = bytearray(64)
    raw[:2] = b"MZ"
    struct.pack_into("<I", raw, 0x3C, 0xFFFFFFF0)
    path.write_bytes(raw)

    result = analyze_executable(path)

    assert not result.valid
    assert "outside the file" in result.reason


def test_rejects_section_that_extends_past_eof(tmp_path):
    path = make_pe(tmp_path / "truncated.exe")
    raw = bytearray(path.read_bytes())
    section_offset = 0x80 + 24 + 224
    struct.pack_into("<I", raw, section_offset + 16, 0x1000)
    path.write_bytes(raw)

    result = analyze_executable(path)

    assert not result.valid
    assert "extends beyond end of file" in result.reason


def test_rva_does_not_map_zero_filled_virtual_tail():
    section = PESection(".data", 0x1000, 0x2000, 0x100, 0x400)

    assert rva_to_file_offset(0x2050, [section]) == 0x450
    assert rva_to_file_offset(0x2200, [section]) is None
    assert rva_range_to_file_offset(0x20F0, 0x10, [section]) == 0x4F0
    assert rva_range_to_file_offset(0x20F0, 0x11, [section]) is None


def test_directory_input_requires_exactly_one_executable(tmp_path):
    make_pe(tmp_path / "a.exe", with_import=False)
    make_pe(tmp_path / "b.EXE", with_import=False)

    try:
        analyze_executable(tmp_path)
    except ValueError as error:
        assert "Multiple executable files" in str(error)
        assert "a.exe" in str(error)
        assert "b.EXE" in str(error)
    else:
        raise AssertionError("Expected directory ambiguity to be rejected")
