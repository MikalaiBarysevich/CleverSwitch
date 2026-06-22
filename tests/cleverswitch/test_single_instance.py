"""Unit tests for the single-instance guard."""

from __future__ import annotations

import pytest
from filelock import FileLock

from src.cleverswitch.errors.errors import AlreadyRunningError
from src.cleverswitch.single_instance import acquire_single_instance_lock


def test_first_acquire_succeeds_and_returns_held_lock(tmp_path):
    lock_path = tmp_path / "cleverswitch.lock"

    lock = acquire_single_instance_lock(lock_path)

    assert isinstance(lock, FileLock)
    assert lock.is_locked
    lock.release()


def test_second_acquire_raises_already_running(tmp_path):
    lock_path = tmp_path / "cleverswitch.lock"

    first = acquire_single_instance_lock(lock_path)
    try:
        with pytest.raises(AlreadyRunningError):
            acquire_single_instance_lock(lock_path)
    finally:
        first.release()


def test_acquire_succeeds_after_first_lock_released(tmp_path):
    lock_path = tmp_path / "cleverswitch.lock"

    first = acquire_single_instance_lock(lock_path)
    first.release()

    second = acquire_single_instance_lock(lock_path)
    assert second.is_locked
    second.release()


def test_acquire_creates_parent_directory(tmp_path):
    lock_path = tmp_path / "nested" / "dir" / "cleverswitch.lock"

    lock = acquire_single_instance_lock(lock_path)

    assert lock_path.parent.is_dir()
    lock.release()
