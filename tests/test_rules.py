from __future__ import annotations

from game.enums import GamePhase
from game.models import GoalCondition, PrivateGoal
from game.rules import collapse_reason, evaluate_private_goal


def test_collapse_condition(engine) -> None:
    engine.state.resources.stability = 0
    assert collapse_reason(engine.state) == "稳定度降至 0"
    engine.state.phase = GamePhase.RESOLUTION
    engine.advance_phase()
    assert engine.state.finished
    assert not engine.state.result.shelter_survived


def test_private_goal_evaluation(engine) -> None:
    player = engine.state.players["player_1"]
    player.private_goal = PrivateGoal(
        "test_goal",
        "修理一次",
        [GoalCondition("repair_count", ">=", 1)],
    )
    player.metrics["repair_count"] = 1
    assert evaluate_private_goal(engine.state, player)
    assert player.private_goal.completed


def test_same_seed_has_same_event_sequence() -> None:
    from game.engine import GameEngine
    from game.models import GameConfig

    first = GameEngine(GameConfig(random_seed=2026))
    second = GameEngine(GameConfig(random_seed=2026))
    assert first.event_order == second.event_order

