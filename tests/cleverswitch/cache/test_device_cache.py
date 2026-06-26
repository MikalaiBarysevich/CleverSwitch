"""Unit tests for cache/device_cache.py."""

from __future__ import annotations

import json

from src.cleverswitch.cache.device_cache import CACHE_VERSION, DeviceCache
from src.cleverswitch.model.logi_device import LogiDevice
from src.cleverswitch.subscriber.task.constants import Task

WPID = 0x407B
PID = 0xAAAA


def _keyboard():
    d = LogiDevice(
        wpid=WPID,
        pid=PID,
        slot=1,
        role="keyboard",
        available_features={0x0005: 4, 0x0007: 6, 0x1814: 9, 0x1B04: 5},
        name="Wireless Keyboard MX Keys",
        friendly_name="MX Keys",
        supported_flags={0x20, 0x40},
    )
    d.pending_steps = set()
    return d


def _mouse():
    d = LogiDevice(
        wpid=0x4082,
        pid=PID,
        slot=2,
        role="mouse",
        available_features={0x0005: 3, 0x0007: 5, 0x1814: 7},
        name="MX Master 3",
        friendly_name="MX Master 3",
    )
    d.pending_steps = set()
    return d


# ── load: graceful degradation (must never raise at startup) ─────────────────────


def test_load_missing_file_is_empty(tmp_path):
    cache = DeviceCache(tmp_path / "nope.json")
    cache.load()  # must not raise
    assert cache.find_by_wpid(WPID) is None


def test_load_corrupt_json_degrades(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("{not valid json")
    cache = DeviceCache(path)
    cache.load()  # must not raise
    assert cache.find_by_wpid(WPID) is None


def test_load_non_object_json_degrades(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps(["not", "a", "mapping"]))
    cache = DeviceCache(path)
    cache.load()  # DiskCache(**list) → TypeError, swallowed
    assert cache.find_by_wpid(WPID) is None


def test_load_malformed_devices_ignored(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({"version": CACHE_VERSION, "devices": "not a list"}))
    cache = DeviceCache(path)
    cache.load()  # must not raise
    assert cache.find_by_wpid(WPID) is None


def test_load_unsupported_version_ignored(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({"version": CACHE_VERSION + 99, "devices": []}))
    cache = DeviceCache(path)
    cache.load()
    assert cache.find_by_wpid(WPID) is None


def test_load_skips_malformed_entry_keeps_siblings(tmp_path):
    path = tmp_path / "cache.json"
    cache = DeviceCache(path)
    cache.save(_keyboard())  # valid sibling written

    data = json.loads(path.read_text())
    data["devices"].append({"role": "mouse"})  # entry missing required keys
    path.write_text(json.dumps(data))

    cache2 = DeviceCache(path)
    cache2.load()  # must not raise
    survivor = cache2.find_by_wpid(WPID)
    assert survivor is not None
    assert survivor.role == "keyboard"


def test_save_swallows_write_error(tmp_path, mocker):
    path = tmp_path / "cache.json"
    cache = DeviceCache(path)
    mocker.patch("src.cleverswitch.cache.device_cache.os.replace", side_effect=OSError("disk full"))
    cache.save(_keyboard())  # must not raise
    # in-memory entry still registered even though the disk write failed
    assert cache.find_by_wpid(WPID).role == "keyboard"


# ── round-trip + encoding ────────────────────────────────────────────────────────


def test_save_then_load_round_trip(tmp_path):
    path = tmp_path / "cache.json"
    DeviceCache(path).save(_keyboard())

    reloaded = DeviceCache(path)
    reloaded.load()
    device = reloaded.find_by_wpid(WPID)

    assert device is not None
    assert device.role == "keyboard"
    assert device.available_features == {0x0005: 4, 0x0007: 6, 0x1814: 9, 0x1B04: 5}
    assert device.name == "Wireless Keyboard MX Keys"
    assert device.friendly_name == "MX Keys"
    assert device.supported_flags == {0x20, 0x40}
    assert device.pending_steps == set()


def test_save_persists_pending_steps(tmp_path):
    path = tmp_path / "cache.json"
    partial = _keyboard()
    partial.name = None
    partial.pending_steps = {Task.Name.GET_DEVICE_NAME}
    DeviceCache(path).save(partial)

    reloaded = DeviceCache(path)
    reloaded.load()
    device = reloaded.find_by_wpid(WPID)

    assert device.name is None
    assert device.pending_steps == {Task.Name.GET_DEVICE_NAME}


def test_find_by_wpid_returns_none_for_unknown(tmp_path):
    cache = DeviceCache(tmp_path / "cache.json")
    cache.save(_keyboard())
    assert cache.find_by_wpid(0xDEAD) is None


def test_multiple_devices_round_trip(tmp_path):
    path = tmp_path / "cache.json"
    cache = DeviceCache(path)
    cache.save(_keyboard())
    cache.save(_mouse())

    reloaded = DeviceCache(path)
    reloaded.load()
    assert reloaded.find_by_wpid(WPID).role == "keyboard"
    assert reloaded.find_by_wpid(0x4082).role == "mouse"


# ── atomic write ─────────────────────────────────────────────────────────────────


def test_atomic_write_uses_replace(tmp_path, mocker):
    path = tmp_path / "cache.json"
    spy = mocker.spy(__import__("os"), "replace")
    DeviceCache(path).save(_keyboard())
    assert spy.call_count == 1
    assert path.exists()
    assert not (tmp_path / "cache.json.tmp").exists()


# ── clear ────────────────────────────────────────────────────────────────────────


def test_clear_removes_file_and_entries(tmp_path):
    path = tmp_path / "cache.json"
    cache = DeviceCache(path)
    cache.save(_keyboard())
    assert path.exists()

    cache.clear()

    assert not path.exists()
    assert cache.find_by_wpid(WPID) is None


def test_clear_missing_file_is_noop(tmp_path):
    cache = DeviceCache(tmp_path / "nope.json")
    cache.clear()  # must not raise


def test_clear_swallows_unlink_error(tmp_path, mocker):
    path = tmp_path / "cache.json"
    cache = DeviceCache(path)
    cache.save(_keyboard())
    mocker.patch.object(type(path), "unlink", side_effect=OSError("locked"))
    cache.clear()  # must not raise
    assert cache.find_by_wpid(WPID) is None  # in-memory still reset


def test_save_overwrites_existing_entry(tmp_path):
    path = tmp_path / "cache.json"
    cache = DeviceCache(path)
    cache.save(_keyboard())

    changed = _keyboard()
    changed.friendly_name = "Renamed"
    cache.save(changed)

    reloaded = DeviceCache(path)
    reloaded.load()
    assert reloaded.find_by_wpid(WPID).friendly_name == "Renamed"
