import pytest

from app.storage import init_db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "veriagent-test.db"
    monkeypatch.setenv("VERIAGENT_DB_PATH", str(db_path))
    init_db(db_path)
    yield db_path
