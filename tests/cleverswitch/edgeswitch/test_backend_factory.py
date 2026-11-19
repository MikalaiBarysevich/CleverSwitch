from unittest.mock import MagicMock

from cleverswitch.edgeswitch import backend_factory
from cleverswitch.edgeswitch.backend_factory import create_backend, start_edge_switch
from cleverswitch.errors.errors import EdgeSwitchError
from cleverswitch.model.config.edge import Edge
from cleverswitch.model.config.edge_switch_config import EdgeSwitchConfig

ENABLED = EdgeSwitchConfig(enabled=True, edges={Edge.LEFT: 0})


def test_disabled_config_starts_nothing(mocker):
    create = mocker.patch.object(backend_factory, "create_backend")
    assert start_edge_switch(EdgeSwitchConfig(), MagicMock()) is None
    create.assert_not_called()


def test_starts_the_created_backend(mocker):
    backend = MagicMock()
    mocker.patch.object(backend_factory, "create_backend", return_value=backend)
    assert start_edge_switch(ENABLED, MagicMock()) is backend
    backend.start.assert_called_once()


def test_no_backend_for_platform_returns_none(mocker):
    mocker.patch.object(backend_factory, "create_backend", return_value=None)
    assert start_edge_switch(ENABLED, MagicMock()) is None


def test_backend_that_cannot_start_yet_is_kept_for_revival(mocker, caplog):
    backend = MagicMock()
    backend.start.side_effect = EdgeSwitchError("no permission")
    mocker.patch.object(backend_factory, "create_backend", return_value=backend)
    assert start_edge_switch(ENABLED, MagicMock()) is backend
    backend.stop.assert_not_called()
    assert "not running: no permission" in caplog.text


def test_backend_that_fails_unexpectedly_is_stopped(mocker, caplog):
    backend = MagicMock()
    backend.start.side_effect = RuntimeError("boom")
    mocker.patch.object(backend_factory, "create_backend", return_value=backend)
    assert start_edge_switch(ENABLED, MagicMock()) is None
    backend.stop.assert_called_once()


def test_unexpected_error_is_a_warning(mocker, caplog):
    mocker.patch.object(backend_factory, "create_backend", side_effect=OSError("boom"))
    assert start_edge_switch(ENABLED, MagicMock()) is None
    assert "unexpected error" in caplog.text


def test_create_backend_warns_platform_not_supported_yet(mocker, caplog):
    mocker.patch.object(backend_factory, "get_system", return_value="Plan9")
    assert create_backend(ENABLED, MagicMock()) is None
    assert "not supported" in caplog.text


def test_windows_gets_a_raw_input_backend(mocker):
    from cleverswitch.edgeswitch.loop_backend import LoopEdgeBackend

    mocker.patch.object(backend_factory, "get_system", return_value="Windows")
    backend = create_backend(ENABLED, MagicMock())
    assert isinstance(backend, LoopEdgeBackend)
    assert backend._name == "edge-windows"


def test_macos_gets_an_event_tap_backend(mocker):
    from cleverswitch.edgeswitch.loop_backend import LoopEdgeBackend

    mocker.patch.object(backend_factory, "get_system", return_value="Darwin")
    backend = create_backend(ENABLED, MagicMock())
    assert isinstance(backend, LoopEdgeBackend)
    assert backend._name == "edge-macos"


def test_linux_picks_its_reader_per_desktop(mocker):
    from cleverswitch.edgeswitch.linux import desktop
    from cleverswitch.edgeswitch.loop_backend import LoopEdgeBackend

    factory = mocker.spy(desktop, "linux_loop_factory")
    mocker.patch.object(backend_factory, "get_system", return_value="Linux")
    backend = create_backend(EdgeSwitchConfig(enabled=True, edges={Edge.LEFT: 0}, cooldown_ms=250), MagicMock())
    assert isinstance(backend, LoopEdgeBackend)
    assert backend._name == "edge-linux"
    assert factory.call_args.args[0]()._cooldown_s == 0.25


def test_every_attempt_gets_a_fresh_detector():
    """A revived backend builds a new loop; it must not inherit the armed/latched state of the dead one."""
    factory = backend_factory._detector_factory(ENABLED)
    assert factory() is not factory()
