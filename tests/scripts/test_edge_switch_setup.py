"""Tests for the installer's edge-switch wizard (scripts/edge_switch_setup.sh).

The wizard is shell, so each case runs it the way an installer does: bash sourcing the helper with a piped
answer list and a throwaway HOME. The config it writes is then parsed with the real loader.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from cleverswitch.config.config import _parse_edge_switch
from cleverswitch.model.config.edge import Edge
from cleverswitch.model.config.modifier import Modifier

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "scripts" / "edge_switch_setup.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(
    BASH is None or sys.platform == "win32", reason="the wizard is bash and does not run on Windows here"
)

CONFIG = Path(".config/cleverswitch/config.yaml")


def _run(
    home: Path,
    answers: str,
    desktop: str = "",
    extension_dir: str = "",
    data_home: str = "",
    wayland: bool = False,
) -> subprocess.CompletedProcess:
    # X11 by default so the desktop is supported without a compositor; no desktop name means no GNOME work.
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "XDG_SESSION_TYPE": "x11",
        "DISPLAY": ":0",
        "XDG_CURRENT_DESKTOP": desktop,
    }
    if wayland:
        env["XDG_SESSION_TYPE"] = "wayland"
        env["WAYLAND_DISPLAY"] = "wayland-0"
        env.pop("DISPLAY")
    if data_home:
        env["XDG_DATA_HOME"] = data_home
    script = f'set -euo pipefail; . "{HELPER}"; es_configure_linux "{extension_dir}"'
    return subprocess.run(
        [BASH, "-c", script],
        input=answers,
        text=True,
        capture_output=True,
        env=env,
        timeout=30,
        check=False,
    )


def _edge_switch(home: Path):
    data = yaml.safe_load((home / CONFIG).read_text())
    return _parse_edge_switch(data), data


def test_writes_a_new_config(tmp_path):
    result = _run(tmp_path, "y\n2\n2\n\n\n\n")

    assert result.returncode == 0, result.stderr
    cfg, data = _edge_switch(tmp_path)
    assert cfg.modifiers == Modifier.ALT
    assert cfg.edges == {Edge.LEFT: 1}  # host 2 is 1-based in config
    assert "hooks" not in data


def test_all_edges_left_empty_writes_nothing(tmp_path):
    _run(tmp_path, "y\n1\n\n\n\n\n")

    assert not (tmp_path / CONFIG).exists(), "nothing mapped means nothing to write"


@pytest.mark.parametrize("bad", ["0", "4", "x", "-1"])
def test_hosts_outside_one_to_three_are_rejected(tmp_path, bad):
    result = _run(tmp_path, f"y\n1\n{bad}\n2\n\n\n\n")

    assert result.returncode == 0
    cfg, _ = _edge_switch(tmp_path)
    assert cfg.edges == {Edge.LEFT: 1}


def test_appending_keeps_the_existing_keys(tmp_path):
    config = tmp_path / CONFIG
    config.parent.mkdir(parents=True)
    config.write_text("hooks:\n  h:\n    path: /bin/true\n    type: CONNECT\n")

    _run(tmp_path, "y\n1\n1\n2\n\n\n")

    cfg, data = _edge_switch(tmp_path)
    assert cfg.edges == {Edge.LEFT: 0, Edge.RIGHT: 1}
    assert list(data["hooks"]) == ["h"]


FIXTURE_WITH_COMMENT = """\
edge_switch:
  modifier: ctrl
  edges:
    left: 1

# Hooks run on events
hooks:
  h:
    path: /bin/true
    type: CONNECT
"""


def test_replacing_keeps_the_comment_below_the_block(tmp_path):
    config = tmp_path / CONFIG
    config.parent.mkdir(parents=True)
    config.write_text(FIXTURE_WITH_COMMENT)
    config.chmod(0o640)

    result = _run(tmp_path, "y\n1\n3\n\n\n\ny\n")

    assert result.returncode == 0, result.stderr
    text = config.read_text()
    assert "# Hooks run on events" in text
    cfg, data = _edge_switch(tmp_path)
    assert cfg.edges == {Edge.LEFT: 2}
    assert list(data["hooks"]) == ["h"]
    assert stat.S_IMODE(config.stat().st_mode) == 0o640, "the rewrite must keep the file mode"


def test_refusing_the_replacement_leaves_the_file_alone(tmp_path):
    config = tmp_path / CONFIG
    config.parent.mkdir(parents=True)
    config.write_text(FIXTURE_WITH_COMMENT)

    _run(tmp_path, "y\n1\n3\n\n\n\nn\n")

    assert config.read_text() == FIXTURE_WITH_COMMENT


def test_a_block_at_end_of_file_is_replaced(tmp_path):
    config = tmp_path / CONFIG
    config.parent.mkdir(parents=True)
    config.write_text("logging:\n  level: INFO\n\nedge_switch:\n  modifier: ctrl\n  edges:\n    left: 1\n")

    _run(tmp_path, "y\n4\n\n2\n\n\ny\n")

    cfg, data = _edge_switch(tmp_path)
    assert cfg.modifiers == Modifier.META
    assert cfg.edges == {Edge.RIGHT: 1}
    assert data["logging"] == {"level": "INFO"}


def test_an_unmapped_block_is_not_written_as_enabled(tmp_path):
    result = _run(tmp_path, "y\n1\n\n\n\n\n")

    assert "No edge was mapped" in result.stdout
    assert "enabled: false" in result.stdout


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="root ignores directory permissions")
def test_an_unwritable_config_is_a_warning_not_a_failed_install(tmp_path):
    config_dir = tmp_path / CONFIG.parent
    config_dir.mkdir(parents=True)
    config_dir.chmod(0o500)
    try:
        result = _run(tmp_path, "y\n1\n1\n\n\n\n")
    finally:
        config_dir.chmod(0o700)

    assert result.returncode == 0, "the wizard must not abort the installer"
    assert "Could not write" in result.stdout
    assert not (tmp_path / CONFIG).exists()


def test_an_answer_without_a_trailing_newline_is_kept(tmp_path):
    config = tmp_path / CONFIG
    config.parent.mkdir(parents=True)
    config.write_text(FIXTURE_WITH_COMMENT)

    # The last "y" has no newline after it; read() must keep the character it got at EOF.
    _run(tmp_path, "y\n1\n2\n\n\n\ny")

    cfg, _ = _edge_switch(tmp_path)
    assert cfg.edges == {Edge.LEFT: 1}


def test_a_nested_edge_switch_is_not_mistaken_for_the_top_level_one(tmp_path):
    config = tmp_path / CONFIG
    config.parent.mkdir(parents=True)
    config.write_text("hooks:\n  h:\n    edge_switch: keep me\n")

    _run(tmp_path, "y\n1\n1\n\n\n\n")

    cfg, data = _edge_switch(tmp_path)
    assert cfg.edges == {Edge.LEFT: 0}
    assert data["hooks"]["h"]["edge_switch"] == "keep me"


def test_the_extension_follows_xdg_data_home(tmp_path):
    extension = tmp_path / "gnome-extension" / "cleverswitch@mikalaibarysevich.github.io"
    extension.mkdir(parents=True)
    (extension / "metadata.json").write_text("{}")
    data_home = tmp_path / "data"

    result = _run(
        tmp_path,
        "y\n1\n1\n\n\n\n",
        desktop="GNOME",
        extension_dir=str(tmp_path / "gnome-extension"),
        data_home=str(data_home),
        wayland=True,
    )

    assert result.returncode == 0, result.stderr
    copied = data_home / "gnome-shell" / "extensions" / "cleverswitch@mikalaibarysevich.github.io" / "metadata.json"
    assert copied.is_file()


def test_a_modifier_outside_the_menu_is_rejected(tmp_path):
    _run(tmp_path, "y\n9\n2\n1\n\n\n\n")

    cfg, _ = _edge_switch(tmp_path)
    assert cfg.modifiers == Modifier.ALT


def test_a_second_section_is_removed_too(tmp_path):
    config = tmp_path / CONFIG
    config.parent.mkdir(parents=True)
    config.write_text(
        "hooks:\n  h:\n    path: /bin/true\n\n"
        "edge_switch:\n  modifier: ctrl\n  edges:\n    left: 1\n\n"
        "edge_switch:\n  modifier: alt\n  edges:\n    right: 3\n"
    )

    _run(tmp_path, "y\n1\n2\n\n\n\ny\n")

    text = config.read_text()
    assert sum(1 for line in text.splitlines() if line.startswith("edge_switch:")) == 1
    cfg, data = _edge_switch(tmp_path)
    assert cfg.edges == {Edge.LEFT: 1}
    assert list(data["hooks"]) == ["h"]


def test_a_commented_example_is_not_touched(tmp_path):
    config = tmp_path / CONFIG
    config.parent.mkdir(parents=True)
    config.write_text("# edge_switch:\n#   modifier: ctrl\nedge_switch:\n  modifier: ctrl\n  edges:\n    left: 1\n")

    _run(tmp_path, "y\n1\n2\n\n\n\ny\n")

    text = config.read_text()
    assert "# edge_switch:" in text
    assert "#   modifier: ctrl" in text
    assert sum(1 for line in text.splitlines() if line.startswith("edge_switch:")) == 1
