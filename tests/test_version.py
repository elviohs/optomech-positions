import re
from pathlib import Path

from version import __version__


def test_version_matches_changelog():
    text = (Path(__file__).resolve().parents[1] / "CHANGELOG.md").read_text(encoding="utf-8")
    first = re.search(r"^## (\d+\.\d+\.\d+)", text, re.M).group(1)
    assert first == __version__, "Actualiza version.py o CHANGELOG.md"
