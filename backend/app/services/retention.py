import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AuditEvent, GradingBatch, GradingResult

log = logging.getLogger(__name__)
SWEEP_SECONDS = 600


def purge_content(result: GradingResult) -> None:
    result.attachments = []
    result.submission_text = result.ai_output = result.suggested_feedback = None
    result.final_feedback = result.review_comments = None


async def purge_expired(session: AsyncSession, now: datetime) -> int:
    expired = GradingBatch.expires_at <= now
    results = (await session.execute(
        delete(GradingResult)
        .where(GradingResult.batch_id.in_(select(GradingBatch.id).where(expired)))
        .returning(GradingResult.batch_id, GradingResult.id)
    )).all()
    batches = (await session.scalars(delete(GradingBatch).where(expired).returning(GradingBatch.id))).all()
    session.add_all([AuditEvent(action="deleted", batch_id=b, result_id=r) for b, r in results])
    session.add_all([AuditEvent(action="deleted", batch_id=b) for b in batches])
    await session.commit()
    return len(results) + len(batches)


async def sweep_forever(sessions: async_sessionmaker) -> None:
    while True:
        try:
            async with sessions() as session:
                log.info("retention purge", extra={"count": await purge_expired(session, datetime.now(UTC))})
        except Exception as exc:
            log.error("retention sweep failed", exc_info=exc)
        await asyncio.sleep(SWEEP_SECONDS)
