from __future__ import annotations

from game.enums import Faction, GamePhase, HealthStatus, Visibility
from game.models import ExpulsionCase


def _expel_survivor(engine):
    target = next(item for item in engine.state.players.values() if item.hidden_faction == Faction.SURVIVOR)
    voters = [item for item in engine.state.players.values() if item.id != target.id]
    engine.state.day = 2
    engine.state.phase = GamePhase.EXPULSION
    engine.state.expulsion = ExpulsionCase(day=2)
    engine.nominate_for_expulsion(voters[0].id, target.id)
    engine.nominate_for_expulsion(voters[1].id, target.id)
    for player in list(engine.state.players.values())[:4]:
        engine.vote_expulsion(player.id, True)
    engine.advance_phase()
    return target


def test_wrong_expulsion_reduces_stability_by_eight(engine) -> None:
    before = engine.state.resources.stability
    target = _expel_survivor(engine)
    assert target.health == HealthStatus.EXPELLED
    assert engine.state.resources.stability == before - 8


def test_identity_not_revealed_immediately_after_expulsion(engine) -> None:
    target = _expel_survivor(engine)
    public_messages = " ".join(
        entry.message for entry in engine.state.logs if entry.visibility == Visibility.PUBLIC
    )
    assert target.hidden_faction.value not in public_messages
    player_view = next(item for item in engine.get_public_state("player_2")["players"] if item["id"] == target.id)
    assert "revealed_faction" not in player_view

