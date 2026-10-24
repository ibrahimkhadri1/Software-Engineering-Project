import asyncio
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.models import GradingBatch, GradingResult
from app.domain.rubric import rubric_parser
from app.main import create_app

# The apps and the alembic subprocess read this, so tests never touch the dev database.
TEST_DB = make_url(get_settings().database_url).set(database="autograder_test")
os.environ["DATABASE_URL"] = TEST_DB.render_as_string(hide_password=False)
get_settings.cache_clear()
TABLES = "grading_results, grading_batches, audit_events"

GRADER = "auth0|grader"
SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJwks:
    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=SIGNING_KEY.public_key())


def token(sub=GRADER, permissions=("use:autograder",), key=SIGNING_KEY, **claims) -> str:
    settings = get_settings()
    now = int(time.time())
    return jwt.encode({"sub": sub, "aud": settings.auth0_audience, "iss": f"https://{settings.auth0_domain}/",
                       "iat": now, "exp": now + 600, "permissions": list(permissions)} | claims, key, "RS256")

RUBRIC_TEXT = """
Correctness: 10 points - Program produces the right output
Style: 5 pts
Concepts: 6 [keywords: loop, recursion, base case; 2 each] names the key ideas
Total: 21
"""


@pytest.fixture
def rubric():
    return rubric_parser(RUBRIC_TEXT)


def make_pdf(lines: list[str]) -> bytes:
    text = " ".join("(" + line.replace("(", r"\(").replace(")", r"\)") + ") Tj T*" for line in lines)
    content = f"BT /F1 12 Tf 14 TL 72 720 Td {text} ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        " /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = "%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return out.encode("latin-1")


async def _create_test_database() -> None:
    engine = create_async_engine(TEST_DB.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        if not await conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = 'autograder_test'")):
            await conn.execute(text("CREATE DATABASE autograder_test"))
    await engine.dispose()


@pytest.fixture(scope="session")
def database():
    asyncio.run(_create_test_database())
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, capture_output=True)


async def _truncate() -> None:
    engine = create_async_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES}"))
    await engine.dispose()


@pytest.fixture
async def sessions(database):
    await _truncate()
    engine = create_async_engine(TEST_DB)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def api(database):
    asyncio.run(_truncate())
    app = create_app()
    app.state.jwks = FakeJwks()
    with TestClient(app, headers={"Authorization": f"Bearer {token()}"}) as client:
        yield client


async def add_result(sessions, expires_in=timedelta(hours=48), **fields):
    async with sessions() as session:
        batch = GradingBatch(auth0_sub=GRADER, course_id="1001", assignment_id="2001", assignment_name="Lab 3",
                             rubric_text=RUBRIC_TEXT, expires_at=datetime.now(UTC) + expires_in)
        result = GradingResult(**{"course_id": "1001", "assignment_id": "2001", "student_id": "3001",
                                  "student_name": "Ada Lovelace", "attempt": "1", "file_type": "online_text"} | fields)
        batch.results.append(result)
        session.add(batch)
        await session.commit()
        return result.id
