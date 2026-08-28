from runexe.resources import (
    _decode_manifest,
    _parse_version_info,
    extract_requested_execution_level,
)

from .helpers import make_version_info


def test_parses_binary_fixed_info_and_string_children():
    info = _parse_version_info(make_version_info())

    assert info.file_version == "1.2.3.4"
    assert info.product_version == "5.6.7.8"
    assert info.strings["ProductName"] == "RunEXE"


def test_extracts_namespaced_execution_level_case_insensitively():
    manifest = '<asmv3:requestedExecutionLevel uiAccess="false" level="requireAdministrator" />'

    assert extract_requested_execution_level(manifest) == "requireAdministrator"


def test_decodes_utf16_manifest_without_bom():
    manifest = "<assembly>✓</assembly>"

    assert _decode_manifest(manifest.encode("utf-16-le")) == manifest
