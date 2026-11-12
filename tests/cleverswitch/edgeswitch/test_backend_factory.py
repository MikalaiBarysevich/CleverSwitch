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


def test_backend_that_cannot_start_is_a_warning(mocker, caplog):
    backend = MagicMock()
    backend.start.side_effect = EdgeSwitchError("no permission")
    mocker.patch.object(backend_factory, "create_backend", return_value=backend)
    assert start_edge_switch(ENABLED, MagicMock()) is None
    assert "Edge switch disabled: no permission" in caplog.text


def test_unexpected_error_is_a_warning(mocker, caplog):
    mocker.patch.object(backend_factory, "create_backend", side_effect=OSError("boom"))
    assert start_edge_switch(ENABLED, MagicMock()) is None
    assert "unexpected error" in caplog.text


def test_create_backend_warns_platform_not_supported_yet(caplog):
    assert create_backend(ENABLED, MagicMock()) is None
    assert "not supported" in caplog.text
