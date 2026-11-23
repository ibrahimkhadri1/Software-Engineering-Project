import subprocess
import sys

import pytest
from conftest import add_result
from sqlalchemy.exc import IntegrityError

from app.domain.status import Status


@pytest.mark.anyio
async def test_a_submission_attempt_is_claimed_for_publishing_once(sessions):
    """TC-006 database backstop: a second claim on the same attempt fails even from another batch."""
    await add_result(sessions, status=Status.PUBLISHED)
    await add_result(sessions, status=Status.APPROVED)
    await add_result(sessions, status=Status.PUBLISHING, attempt="2")
    with pytest.raises(IntegrityError):
        await add_result(sessions, status=Status.PUBLISHING)


def test_migrations_match_the_models(database):
    check = subprocess.run([sys.executable, "-m", "alembic", "check"], capture_output=True, text=True)
    assert check.returncode == 0, check.stderr
