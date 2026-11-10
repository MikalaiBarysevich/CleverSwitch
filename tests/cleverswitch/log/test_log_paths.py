from pathlib import Path

import pytest

from cleverswitch.log.log_paths import default_log_path

HOME = Path("/home/u")


@pytest.mark.parametrize(
    ("system", "env", "expected"),
    [
        ("Linux", {}, HOME / ".local/state/cleverswitch/cleverswitch.log"),
        ("Linux", {"XDG_STATE_HOME": "/xdg"}, Path("/xdg/cleverswitch/cleverswitch.log")),
        ("Linux", {"XDG_STATE_HOME": "relative"}, HOME / ".local/state/cleverswitch/cleverswitch.log"),
        ("Linux", {"XDG_STATE_HOME": ""}, HOME / ".local/state/cleverswitch/cleverswitch.log"),
        ("Darwin", {"XDG_STATE_HOME": "/xdg"}, HOME / "Library/Logs/CleverSwitch/cleverswitch.log"),
        ("Windows", {"LOCALAPPDATA": "/lad"}, Path("/lad/CleverSwitch/Logs/cleverswitch.log")),
        ("Windows", {}, HOME / "AppData/Local/CleverSwitch/Logs/cleverswitch.log"),
    ],
)
def test_default_log_path(system, env, expected):
    assert default_log_path(system, env, HOME) == expected
