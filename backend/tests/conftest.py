import pytest

from app.storage import init_db


TEST_RECEIPT_SECRET = "test-receipt-secret-for-pytest"
TEST_ADMIN_API_KEY = "test-admin-api-key-for-pytest"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "veriagent-test.db"
    monkeypatch.setenv("VERIAGENT_DB_PATH", str(db_path))
    monkeypatch.setenv("VERIAGENT_RECEIPT_SECRET", TEST_RECEIPT_SECRET)
    monkeypatch.setenv("VERIAGENT_ADMIN_API_KEY", TEST_ADMIN_API_KEY)
    init_db(db_path)
    yield db_path
