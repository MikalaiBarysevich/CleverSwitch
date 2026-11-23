"""The bundled GNOME Shell extension repeats constants the daemon also holds, and it is installed once, by
hand, from the release archive. Nothing links the two at run time, so pin them here: a rename or a changed
tolerance would otherwise fail silently on the GNOME side only."""

from __future__ import annotations

import json
import re
from pathlib import Path

from cleverswitch.edgeswitch.geometry import EDGE_TOLERANCE_PX
from cleverswitch.edgeswitch.linux.edge_bus import BUS_NAME, INTERFACE, OBJECT_PATH
from cleverswitch.edgeswitch.linux.gnome_shell import EXTENSION_UUID

EXTENSION_DIR = Path(__file__).resolve().parents[4] / "gnome-extension" / EXTENSION_UUID


def _source() -> str:
    return (EXTENSION_DIR / "extension.js").read_text()


def test_the_extension_talks_to_the_same_bus_name_path_and_interface():
    source = _source()
    assert f"const NAME = '{BUS_NAME}'" in source
    assert f"const PATH = '{OBJECT_PATH}'" in source
    assert f"const IFACE = '{INTERFACE}'" in source


def test_the_extension_uses_the_same_edge_tolerance():
    match = re.search(r"const TOLERANCE = ([0-9.]+);", _source())
    assert match, "the extension no longer declares TOLERANCE"
    assert float(match.group(1)) == EDGE_TOLERANCE_PX


def test_the_extension_metadata_matches_its_directory_and_uuid():
    metadata = json.loads((EXTENSION_DIR / "metadata.json").read_text())
    assert metadata["uuid"] == EXTENSION_UUID
    assert EXTENSION_DIR.name == EXTENSION_UUID


def test_the_extension_declares_the_gnome_versions_the_readme_promises():
    metadata = json.loads((EXTENSION_DIR / "metadata.json").read_text())
    versions = [int(v) for v in metadata["shell-version"]]
    assert min(versions) <= 45, "the README promises GNOME 45 or newer"
    assert max(versions) >= 51
