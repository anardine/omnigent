"""Tests for the ``omnigent debug db-upgrade`` command (omnigent.cli)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from sqlalchemy import create_engine, text

from omnigent.cli import cli
from omnigent.db.utils import _build_alembic_config, _get_head_db_revision


def _make_db_at_head(db_path: Path) -> str:
    """Create a SQLite DB migrated to head; return its SQLAlchemy URI."""
    from alembic import command

    uri = f"sqlite:///{db_path}"
    head = _get_head_db_revision(uri)
    engine = create_engine(uri)
    config = _build_alembic_config(uri)
    try:
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, head)
    finally:
        engine.dispose()
    return uri


def test_db_upgrade_missing_sqlite_file_errors_with_path(tmp_path: Path) -> None:
    """
    A SQLite URL whose file doesn't exist fails with a clear,
    path-naming message instead of SQLite's opaque "unable to open
    database file" — the exact confusion from the crash report, where
    the parent directory was missing.
    """
    missing = tmp_path / "does-not-exist" / "chat.db"
    result = CliRunner().invoke(cli, ["debug", "db-upgrade", f"sqlite:///{missing}"])

    assert result.exit_code != 0
    assert str(missing) in result.output
    assert str(missing.parent) in result.output
    assert "does not exist" in result.output


def test_db_upgrade_unknown_revision_diagnoses_version_mismatch(tmp_path: Path) -> None:
    """
    A DB stamped at a revision this install doesn't ship (created by a
    newer Omnigent) is diagnosed as a version mismatch — not surfaced as
    Alembic's raw "Can't locate revision" traceback.
    """
    db_path = tmp_path / "newer.db"
    uri = _make_db_at_head(db_path)
    bogus = "deadbeef0000"
    engine = create_engine(uri)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE alembic_version SET version_num = :rev"),
                {"rev": bogus},
            )
    finally:
        engine.dispose()

    result = CliRunner().invoke(cli, ["debug", "db-upgrade", uri])

    assert result.exit_code != 0
    assert bogus in result.output
    assert "newer" in result.output
    assert "Can't locate revision" not in result.output


def test_db_upgrade_at_head_is_clean_noop(tmp_path: Path) -> None:
    """A DB already at head upgrades cleanly and reports completion."""
    uri = _make_db_at_head(tmp_path / "at_head.db")
    result = CliRunner().invoke(cli, ["debug", "db-upgrade", uri])

    assert result.exit_code == 0, result.output
    assert "Upgrade complete." in result.output
