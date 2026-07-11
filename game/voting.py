from __future__ import annotations

from game.enums import ProposalStatus, VoteChoice
from game.models import Proposal


def resolve_vote(proposal: Proposal, eligible_voter_ids: set[str]) -> ProposalStatus:
    """Pass only when support exceeds half of all currently eligible voters."""
    support = sum(
        choice == VoteChoice.SUPPORT
        for voter_id, choice in proposal.votes.items()
        if voter_id in eligible_voter_ids
    )
    proposal.status = (
        ProposalStatus.PASSED
        if support > len(eligible_voter_ids) / 2
        else ProposalStatus.FAILED
    )
    return proposal.status

