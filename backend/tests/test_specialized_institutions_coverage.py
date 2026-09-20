import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_specialized_institutions_coverage_01.py"
SPEC = importlib.util.spec_from_file_location("specialized_coverage", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_master_is_unique_and_valid():
    rows = MODULE.load_master()
    assert len(rows) >= 30
    assert len({row["name"] for row in rows}) == len(rows)
    assert {"sports", "dance", "film", "drama", "media"} == {
        category for row in rows for category in row["category"]
    }


def test_every_category_has_p0():
    rows = MODULE.load_master()
    for category in MODULE.CATEGORIES:
        assert any(category in row["category"] and row["priority"] == "P0" for row in rows)
