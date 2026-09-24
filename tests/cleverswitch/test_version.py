import importlib
from importlib.metadata import PackageNotFoundError

import pytest

import cleverswitch


@pytest.fixture
def reload_cleverswitch():
    yield
    importlib.reload(cleverswitch)


def test_version_comes_from_installed_metadata(mocker, reload_cleverswitch):
    mocker.patch("importlib.metadata.version", return_value="9.8.7")

    importlib.reload(cleverswitch)

    assert cleverswitch.__version__ == "9.8.7"


def test_version_falls_back_when_package_not_installed(mocker, reload_cleverswitch):
    mocker.patch("importlib.metadata.version", side_effect=PackageNotFoundError("cleverswitch"))

    importlib.reload(cleverswitch)

    assert cleverswitch.__version__ == "0.0.0+unknown"
