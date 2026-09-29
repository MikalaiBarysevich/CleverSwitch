import ast
import importlib.util
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "windows" / "gen_version_info.py"


@pytest.fixture
def gen():
    spec = importlib.util.spec_from_file_location("gen_version_info", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("1.5.4", (1, 5, 4, 0)),
        ("1.5.5.dev3+g17999dc.d20260929", (1, 5, 5, 3)),
        ("2.0", (2, 0, 0, 0)),
        ("1.2.3.4", (1, 2, 3, 0)),
    ],
)
def test_to_file_version(gen, version, expected):
    assert gen.to_file_version(version) == expected


def test_render_stamps_fixed_and_string_versions(gen):
    text = gen.render("1.5.5.dev3+g17999dc", "Sync host switching")

    ast.parse(text)
    assert "filevers=(1, 5, 5, 3)" in text
    assert "prodvers=(1, 5, 5, 3)" in text
    assert "StringStruct('FileVersion', '1.5.5.dev3+g17999dc')" in text
    assert "StringStruct('ProductVersion', '1.5.5.dev3+g17999dc')" in text
    assert "StringStruct('FileDescription', 'Sync host switching')" in text


def test_main_writes_version_file(gen, mocker, tmp_path, capsys):
    mocker.patch.object(gen.metadata, "version", return_value="1.5.4")
    mocker.patch.object(gen.metadata, "metadata", return_value={"Summary": "Sync host switching"})
    out = tmp_path / "build" / "version_info.txt"

    assert gen.main(["gen_version_info.py", str(out)]) == 0

    assert "filevers=(1, 5, 4, 0)" in out.read_text(encoding="utf-8")
    assert capsys.readouterr().out.strip() == "1.5.4"


def test_main_fails_when_package_not_installed(gen, mocker, tmp_path):
    mocker.patch.object(gen.metadata, "version", side_effect=PackageNotFoundError("cleverswitch"))
    out = tmp_path / "version_info.txt"

    assert gen.main(["gen_version_info.py", str(out)]) == 1

    assert not out.exists()


def test_main_requires_output_path(gen):
    assert gen.main(["gen_version_info.py"]) == 2
