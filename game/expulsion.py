from __future__ import annotations

from game.models import ExpulsionCase


def nominated_target(case: ExpulsionCase) -> str | None:
    """Select a target only after at least two distinct valid nominations."""
    candidates = [
        (target_id, nominators)
        for target_id, nominators in case.nominations.items()
        if len(nominators) >= 2
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-len(item[1]), item[0]))
    return candidates[0][0]


def expulsion_passed(case: ExpulsionCase, eligible_voter_ids: set[str]) -> bool:
    support = sum(
        bool(choice) for voter_id, choice in case.votes.items() if voter_id in eligible_voter_ids
    )
    return support > len(eligible_voter_ids) / 2

