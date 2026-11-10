from cleverswitch.log.instance_lock import try_lock


def test_first_lock_succeeds_and_second_fails(tmp_path):
    path = tmp_path / "cs.log.lock"
    first = try_lock(path)
    assert first is not None
    try:
        assert try_lock(path) is None
    finally:
        first.close()


def test_lock_is_available_again_after_release(tmp_path):
    path = tmp_path / "cs.log.lock"
    try_lock(path).close()
    second = try_lock(path)
    assert second is not None
    second.close()
