from pathlib import Path

import pytest

from runexe.environments import (
    discover_environments,
    format_size,
    remove_managed_environment,
    write_environment_metadata,
)


def test_discovers_tagged_wine_and_proton_environments(tmp_path):
    wine_root = tmp_path / "prefixes"
    proton_root = tmp_path / "proton"
    wine = wine_root / "editor-123"
    proton = proton_root / "game-456"
    (wine / "drive_c").mkdir(parents=True)
    (proton / "pfx" / "drive_c").mkdir(parents=True)
    (wine / "drive_c" / "sample.bin").write_bytes(b"x" * 2048)
    source = tmp_path / "Editor.exe"
    source.touch()
    write_environment_metadata(
        wine,
        backend="wine",
        source=source,
        architecture="x86_64",
        runtime="Wine 11",
        windows_version="11",
    )
    # A later configuration/open action without an override keeps the known
    # reported Windows version instead of erasing it from inventory metadata.
    write_environment_metadata(
        wine,
        backend="wine",
        source=source,
        architecture="x86_64",
        runtime="Wine 11",
        windows_version=None,
    )
    write_environment_metadata(
        proton,
        backend="proton",
        source=tmp_path / "Game.exe",
        architecture="x86_64",
        runtime="Proton Experimental",
        windows_version=None,
    )

    environments = discover_environments((wine_root, proton_root))

    assert {item.backend for item in environments} == {"proton", "wine"}
    wine_info = next(item for item in environments if item.backend == "wine")
    assert wine_info.application == "Editor"
    assert wine_info.runtime == "Wine 11"
    assert wine_info.windows_version == "11"
    assert wine_info.ready
    assert wine_info.size_bytes >= 2048
    assert list(wine.glob(".*.tmp")) == []


def test_removal_is_limited_to_direct_managed_children(tmp_path):
    wine_root = tmp_path / "prefixes"
    proton_root = tmp_path / "proton"
    environment = wine_root / "safe-prefix"
    environment.mkdir(parents=True)
    outside = tmp_path / "do-not-delete"
    outside.mkdir()

    with pytest.raises(ValueError, match="outside"):
        remove_managed_environment(outside, (wine_root, proton_root))

    remove_managed_environment(environment, (wine_root, proton_root))
    assert not environment.exists()
    assert outside.exists()


def test_removal_rejects_symlinks(tmp_path):
    if not hasattr(Path, "symlink_to"):
        pytest.skip("symlinks unavailable")
    wine_root = tmp_path / "prefixes"
    proton_root = tmp_path / "proton"
    outside = tmp_path / "outside"
    outside.mkdir()
    wine_root.mkdir()
    link = wine_root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not permitted")

    with pytest.raises(ValueError, match="unsafe"):
        remove_managed_environment(link, (wine_root, proton_root))
    assert outside.exists()


@pytest.mark.parametrize(
    ("size", "formatted"),
    [(0, "0 B"), (1024, "1.0 KiB"), (5 * 1024**2, "5.0 MiB")],
)
def test_formats_environment_sizes(size, formatted):
    assert format_size(size) == formatted
