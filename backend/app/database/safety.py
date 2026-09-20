from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_SQLITE_PATH = (PROJECT_ROOT / "data" / "v02.sqlite").resolve()


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def _resolved_path(value: str | os.PathLike[str], *, cwd: Path | None = None) -> Path | None:
    text = os.fspath(value)
    if text in {"", ":memory:"} or text.startswith("file::memory:"):
        return None
    if text.startswith("file:"):
        text = text[5:].split("?", 1)[0]
    if re.match(r"^/[A-Za-z]:/", text):
        text = text[1:]
    path = Path(text)
    if not path.is_absolute():
        path = (cwd or Path.cwd()) / path
    return path.resolve()


def sqlite_path_from_url(database_url: str, *, cwd: Path | None = None) -> Path | None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        return None
    return _resolved_path(url.database, cwd=cwd)


def is_test_runtime(*, environment: str | None = None, pytest_active: bool | None = None) -> bool:
    active = "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if pytest_active is not None:
        active = pytest_active
    return (environment or os.environ.get("ENVIRONMENT", "")).lower() == "test" or active


def assert_test_database_is_safe(
    database_url: str,
    *,
    environment: str | None = None,
    pytest_active: bool | None = None,
    production_path: Path = PRODUCTION_SQLITE_PATH,
    cwd: Path | None = None,
) -> None:
    if not is_test_runtime(environment=environment, pytest_active=pytest_active):
        return
    database_path = sqlite_path_from_url(database_url, cwd=cwd)
    if database_path is not None and _same_path(database_path, production_path):
        raise RuntimeError("Tests are not allowed to use the production database")


def assert_test_sqlite_target_is_safe(
    database: str | os.PathLike[str],
    *,
    production_path: Path = PRODUCTION_SQLITE_PATH,
    cwd: Path | None = None,
) -> None:
    database_path = _resolved_path(database, cwd=cwd)
    if database_path is not None and _same_path(database_path, production_path):
        raise RuntimeError("Tests are not allowed to use the production database")
