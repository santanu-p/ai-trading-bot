from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_alembic_upgrade(*, backend_root: Path, database_url: str) -> None:
    original_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    os.environ.setdefault("SESSION_SECRET", "phase9-schema-drift-check")
    try:
        config = Config(str(backend_root / "alembic.ini"))
        config.set_main_option("script_location", str(backend_root / "alembic"))
        command.upgrade(config, "head")
    finally:
        if original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_database_url


def _metadata_tables(backend_root: Path) -> set[str]:
    src = backend_root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from tradingbot.db import Base
    import tradingbot.models  # noqa: F401

    return set(Base.metadata.tables.keys())


def _database_tables(database_url: str) -> set[str]:
    engine = create_engine(database_url, future=True)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def main() -> int:
    backend_root = _backend_root()

    with tempfile.TemporaryDirectory(prefix="phase9-schema-drift-") as temp_dir:
        db_path = Path(temp_dir) / "schema.sqlite3"
        database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"

        _run_alembic_upgrade(backend_root=backend_root, database_url=database_url)
        metadata_tables = _metadata_tables(backend_root)
        migrated_tables = _database_tables(database_url)

    migrated_tables.discard("alembic_version")
    missing_tables = sorted(metadata_tables - migrated_tables)
    extra_tables = sorted(migrated_tables - metadata_tables)

    if missing_tables or extra_tables:
        print("Schema drift detected.")
        if missing_tables:
            print(f"Missing tables after migration: {missing_tables}")
        if extra_tables:
            print(f"Unexpected tables after migration: {extra_tables}")
        return 1

    print("Schema drift check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
