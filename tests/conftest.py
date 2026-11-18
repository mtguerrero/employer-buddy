import os

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/employer_buddy_test"
)
os.environ["WHATSAPP_APP_SECRET"] = "secreto-de-prueba"
os.environ["WHATSAPP_VERIFY_TOKEN"] = "token-de-verificacion"
os.environ["WHATSAPP_TOKEN"] = "token-falso"
os.environ["WHATSAPP_PHONE_NUMBER_ID"] = "123456"
os.environ["ALLOWED_NUMBERS"] = "573001112233"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from employer_buddy.config import get_settings  # noqa: E402
from employer_buddy.db import get_engine, get_sessionmaker  # noqa: E402
from employer_buddy.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
def _clean_db():
    yield
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE jobs, messages, users RESTART IDENTITY CASCADE"))


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def session():
    with get_sessionmaker()() as s:
        yield s


@pytest.fixture
def client():
    return TestClient(app)
