from __future__ import annotations

from game.enums import ProposalStatus


def _proposal(engine):
    engine.advance_phase()  # discussion
    event = engine.state.current_event
    proposal = engine.propose_plan(
        "player_1",
        {
            "title": "规则方案",
            "description": "按事件规则处理",
            "resource_cost": dict(event.resource_cost),
            "participants": ["player_1"],
            "target_event": event.id,
        },
    )
    engine.advance_phase()  # action
    engine.advance_phase()  # voting
    return proposal


def test_strict_majority_passes(engine) -> None:
    proposal = _proposal(engine)
    for index in range(1, 5):
        engine.vote(f"player_{index}", proposal.id, "support")
    for index in range(5, 7):
        engine.vote(f"player_{index}", proposal.id, "oppose")
    engine.advance_phase()
    assert proposal.status == ProposalStatus.PASSED


def test_tie_fails(engine) -> None:
    proposal = _proposal(engine)
    for index in range(1, 4):
        engine.vote(f"player_{index}", proposal.id, "support")
    for index in range(4, 7):
        engine.vote(f"player_{index}", proposal.id, "oppose")
    engine.advance_phase()
    assert proposal.status == ProposalStatus.FAILED


def test_proposal_fails_at_execution_when_resources_are_gone(engine) -> None:
    proposal = _proposal(engine)
    for index in range(1, 5):
        engine.vote(f"player_{index}", proposal.id, "support")
    engine.advance_phase()  # resolution, proposal passed
    for resource in proposal.resource_cost:
        setattr(engine.state.resources, resource, 0)
    engine.advance_phase()  # execute resolution
    assert proposal.status == ProposalStatus.FAILED

