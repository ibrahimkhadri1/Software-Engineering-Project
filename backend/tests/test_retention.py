import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from conftest import add_result
from sqlalchemy import select

from app.db.models import AuditEvent, GradingBatch, GradingResult
from app.services.retention import purge_expired, sweep_forever

pytestmark = pytest.mark.anyio


async def test_expired_batches_are_deleted_with_an_audit_row_each(sessions):
    expired = await add_result(sessions, expires_in=timedelta(hours=1), submission_text="answer")
    kept = await add_result(sessions, expires_in=timedelta(hours=3))
    async with sessions() as session:
        expired_batch = (await session.get(GradingResult, expired)).batch_id
        assert await purge_expired(session, datetime.now(UTC) + timedelta(hours=2)) == 2
        assert (await session.scalars(select(GradingResult.id))).all() == [kept]
        assert await session.get(GradingBatch, expired_batch) is None
        audit = (await session.execute(select(AuditEvent.action, AuditEvent.batch_id, AuditEvent.result_id))).all()
    assert sorted(audit, key=str) == sorted([("deleted", expired_batch, expired), ("deleted", expired_batch, None)],
                                            key=str)


async def test_the_sweep_runs_now_and_survives_failures(sessions, caplog):
    await add_result(sessions, expires_in=timedelta(seconds=-1))
    sweep = asyncio.create_task(sweep_forever(sessions))
    for _ in range(50):
        await asyncio.sleep(0.02)
        async with sessions() as session:
            if not (await session.scalars(select(GradingBatch.id))).all():
                break
    else:
        pytest.fail("expired batch was not swept")
    sweep.cancel()
    assert [r.count for r in caplog.records if r.message == "retention purge"][0] == 2

    def broken():
        raise RuntimeError("database down")

    sweep = asyncio.create_task(sweep_forever(broken))
    await asyncio.sleep(0)
    sweep.cancel()
    assert "retention sweep failed" in caplog.messages
