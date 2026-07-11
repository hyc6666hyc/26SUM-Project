from __future__ import annotations

import pytest

from game.enums import ActionStatus, Faction, GamePhase, Role
from game.exceptions import GameRuleError


def test_action_rejected_when_ap_insufficient(engine) -> None:
    engine.state.phase = GamePhase.ACTION
    player = engine.state.players["player_1"]
    player.ap = 0
    with pytest.raises(GameRuleError, match="AP 不足"):
        engine.perform_action(player.id, {"type": "explore", "target": "outside"})


def test_action_rejected_in_wrong_phase(engine) -> None:
    with pytest.raises(GameRuleError, match="不是行动阶段"):
        engine.perform_action("player_1", {"type": "search", "target": "storage"})


def test_non_saboteur_cannot_sabotage(engine) -> None:
    engine.state.phase = GamePhase.ACTION
    player = next(item for item in engine.state.players.values() if item.hidden_faction == Faction.SURVIVOR)
    player.ap = 2
    with pytest.raises(GameRuleError, match="非破坏者"):
        engine.perform_secret_action(
            player.id, {"type": "sabotage", "target": "water_system"}
        )


def test_facility_durability_changes_after_resolution(engine) -> None:
    engine.state.phase = GamePhase.ACTION
    player = next(item for item in engine.state.players.values() if item.public_role == Role.ENGINEER)
    player.ap = 2
    engine.state.facilities["water_system"].durability = 40
    engine.state.resources.parts = 10
    action = engine.perform_action(player.id, {"type": "repair", "target": "water_system"})
    engine.advance_phase()  # VOTING
    engine.advance_phase()  # RESOLUTION
    engine.advance_phase()  # resolve
    assert action.status == ActionStatus.RESOLVED
    assert engine.state.facilities["water_system"].durability == 65


def test_explore_adds_personal_resources_after_resolution(engine) -> None:
    engine.state.phase = GamePhase.ACTION
    player = engine.state.players["player_1"]
    player.ap = 2
    food_before = player.personal_resources.get("food", 0)
    parts_before = player.personal_resources.get("parts", 0)

    action = engine.perform_action(
        player.id,
        {"type": "explore", "target": "nearby_ruins"},
    )
    assert player.personal_resources.get("food", 0) == food_before

    engine.advance_phase()  # VOTING
    engine.advance_phase()  # RESOLUTION
    engine.advance_phase()  # resolve

    assert action.status == ActionStatus.RESOLVED
    assert player.personal_resources["food"] == food_before + 1
    assert player.personal_resources["parts"] >= parts_before


def test_expelled_player_cannot_act(engine) -> None:
    player = engine.state.players["player_1"]
    from game.enums import HealthStatus

    player.health = HealthStatus.EXPELLED
    player.ap = 2
    engine.state.phase = GamePhase.ACTION
    with pytest.raises(GameRuleError, match="离场玩家"):
        engine.perform_action(player.id, {"type": "search", "target": "storage"})
