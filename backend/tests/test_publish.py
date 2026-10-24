"""TC-006 PublishAttempt (and the TC-009 retry limit)."""
import pytest

from app.domain.publish import DuplicatePublishError, PublishAttempt, PublishError
from app.domain.status import Status


@pytest.fixture
def attempt():
    return PublishAttempt("101", "202", "303", "1")


def test_second_publish_of_the_same_submission_raises(attempt):
    published = set()
    attempt.begin(Status.APPROVED, published)
    attempt.successful()
    published.add(attempt.dedupe_key)
    assert attempt.check_duplicate_submission(published)
    with pytest.raises(DuplicatePublishError):
        attempt.begin(Status.APPROVED, published)
    again = PublishAttempt("101", "202", "303", "1")
    with pytest.raises(DuplicatePublishError):
        again.begin(Status.APPROVED, published)


def test_a_new_submission_attempt_is_a_different_publish(attempt):
    published = {attempt.dedupe_key}
    assert not PublishAttempt("101", "202", "303", "2").check_duplicate_submission(published)


@pytest.mark.parametrize("status", [s for s in Status if s is not Status.APPROVED])
def test_only_approved_results_can_be_published(attempt, status):
    with pytest.raises(PublishError):
        attempt.begin(status, set())


def test_three_tries_with_backoff_then_manual_review(attempt):
    assert attempt.unsuccessful() == 1.0
    assert attempt.unsuccessful() == 2.0
    assert attempt.unsuccessful() is None
    assert attempt.previous_attempts == 3
    with pytest.raises(PublishError, match="attempt limit"):
        attempt.begin(Status.APPROVED, set())
