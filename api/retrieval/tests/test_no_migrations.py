from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_api_owns_no_migration_history() -> None:
    assert list(PROJECT_ROOT.glob("**/migrations/*.py")) == []
