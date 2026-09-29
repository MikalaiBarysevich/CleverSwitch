"""Generate the PyInstaller version file for cleverswitch.exe from the installed package version.

Usage: python gen_version_info.py <output-path>

Run after `pip install .` so the version matches what `cleverswitch --version` reports.
"""

import os
import sys
from importlib import metadata

from packaging.version import Version

TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={file_version},
    prodvers={file_version},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [
            StringStruct('ProductName', 'CleverSwitch'),
            StringStruct('FileDescription', {description!r}),
            StringStruct('FileVersion', {version!r}),
            StringStruct('ProductVersion', {version!r}),
            StringStruct('InternalName', 'cleverswitch'),
            StringStruct('OriginalFilename', 'cleverswitch.exe'),
            StringStruct('LegalCopyright', 'GPL-3.0-or-later')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def to_file_version(version: str) -> tuple[int, int, int, int]:
    parsed = Version(version)
    major, minor, patch = (list(parsed.release) + [0, 0])[:3]
    return major, minor, patch, parsed.dev or 0


def render(version: str, description: str) -> str:
    return TEMPLATE.format(file_version=to_file_version(version), version=version, description=description)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: gen_version_info.py <output-path>", file=sys.stderr)
        return 2

    try:
        version = metadata.version("cleverswitch")
    except metadata.PackageNotFoundError:
        print("cleverswitch is not installed; run 'pip install .' first", file=sys.stderr)
        return 1

    description = metadata.metadata("cleverswitch")["Summary"] or "CleverSwitch"
    os.makedirs(os.path.dirname(argv[1]) or ".", exist_ok=True)
    with open(argv[1], "w", encoding="utf-8") as f:
        f.write(render(version, description))
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
