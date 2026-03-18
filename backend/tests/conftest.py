import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Force local mock generation in tests, regardless of local .env.
os.environ["SILICONFLOW_API_KEY"] = ""

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings.jobs_dir = str(tmp_path / "jobs")
    return TestClient(app)
