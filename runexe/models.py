from dataclasses import dataclass
from pathlib import Path


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
class PEImport:
    name: str


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