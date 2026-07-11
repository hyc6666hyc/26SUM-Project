from __future__ import annotations

from agents.fallback import RuleBasedBot
from game.engine import GameEngine
from game.enums import ActionStatus, Faction, GamePhase
from game.models import GameConfig, GoalCondition, PrivateGoal
from game.rules import evaluate_private_goal, scaled_saboteur_targets


def _saboteur(engine: GameEngine):
    return next(
        player
        for player in engine.state.players.values()
        if player.hidden_faction == Faction.SABOTEUR
    )


def test_hidden_objective_requires_repeated_and_destructive_sabotage(engine) -> None:
    saboteur = _saboteur(engine)
    saboteur.metrics["sabotage_count"] = 3
    saboteur.metrics["lowest_sabotaged_facility_durability"] = 30
    assert not evaluate_private_goal(engine.state, saboteur)

    saboteur.metrics["lowest_sabotaged_facility_durability"] = 25
    assert evaluate_private_goal(engine.state, saboteur)


def test_faction_victories_are_mutually_exclusive(engine) -> None:
    saboteur = _saboteur(engine)
    saboteur.metrics["sabotage_count"] = 3
    saboteur.metrics["lowest_sabotaged_facility_durability"] = 25
    for player in engine.state.players.values():
        if player.hidden_faction == Faction.SURVIVOR:
            player.private_goal = PrivateGoal(
                "survivor_test_goal",
                "测试目标",
                [GoalCondition("world.stability", ">=", 1)],
            )

    engine._finish_game(True, None)

    assert engine.state.result.faction_winner == "SABOTEUR"
    survivor_results = [
        result
        for player_id, result in engine.state.result.player_results.items()
        if engine.state.players[player_id].hidden_faction == Faction.SURVIVOR
    ]
    assert all(result["outcome"] != "完全胜利" for result in survivor_results)
    assert all(result["outcome"] == "避难所存活，但未阻止破坏者" for result in survivor_results)


def test_secret_action_leaves_clue_and_raises_suspicion(engine) -> None:
    saboteur = _saboteur(engine)
    engine.state.phase = GamePhase.ACTION
    saboteur.ap = 2
    action = engine.perform_secret_action(
        saboteur.id,
        {"type": "sabotage", "target": "water_system"},
    )

    engine.advance_phase()  # voting
    engine.advance_phase()  # resolution
    engine.advance_phase()  # resolve actions

    observers = [player for player in engine.state.players.values() if player.id != saboteur.id]
    assert action.status == ActionStatus.RESOLVED
    assert any(player.clues for player in observers)
    assert any(player.relationships[saboteur.id].suspicion > 10 for player in observers)


def test_rule_bot_starts_opposing_survivors_from_day_two(engine) -> None:
    saboteur = _saboteur(engine)
    engine.state.day = 2
    engine.state.phase = GamePhase.ACTION
    saboteur.ap = 2

    decision = RuleBasedBot().decide(engine, saboteur.id)

    assert decision.actions
    assert decision.actions[0].type == "sabotage"


def test_saboteur_goal_scales_with_match_length() -> None:
    expected = {
        1: (1, 75),
        3: (2, 46),
        6: (3, 25),
        10: (5, 20),
    }
    for total_days, targets in expected.items():
        engine = GameEngine(GameConfig(total_days=total_days, random_seed=total_days))
        saboteur = _saboteur(engine)
        conditions = {
            condition.metric: int(condition.value)
            for condition in saboteur.private_goal.conditions
        }
        assert scaled_saboteur_targets(total_days) == targets
        assert conditions["sabotage_count"] == targets[0]
        assert conditions["lowest_sabotaged_facility_durability"] == targets[1]
        assert f"{targets[0]} 次" in saboteur.private_goal.description
        assert f"{targets[1]}%" in saboteur.private_goal.description


def test_one_day_rule_bot_can_attempt_scaled_saboteur_goal() -> None:
    engine = GameEngine(GameConfig(total_days=1, random_seed=31))
    saboteur = _saboteur(engine)
    engine.state.phase = GamePhase.ACTION
    saboteur.ap = 2

    decision = RuleBasedBot().decide(engine, saboteur.id)

    assert decision.actions[0].type == "sabotage"
    assert saboteur.private_goal.conditions[0].value == 1


def test_short_guard_goal_does_not_require_unavailable_expulsion() -> None:
    engine = GameEngine(GameConfig(total_days=2, enable_saboteur=True, random_seed=32))
    guard_goals = [
        player.private_goal
        for player in engine.state.players.values()
        if player.private_goal.id == "guard_protection"
    ]
    assert guard_goals
    assert all(
        condition.metric != "voted_true_saboteur"
        for condition in guard_goals[0].conditions
    )
    assert "短局不要求参与驱逐" in guard_goals[0].description


def test_all_role_goal_numbers_change_between_short_and_long_games() -> None:
    short = GameEngine(
        GameConfig(total_days=1, enable_saboteur=False, random_seed=41)
    )
    long = GameEngine(
        GameConfig(total_days=10, enable_saboteur=False, random_seed=41)
    )

    def conditions_by_goal(engine: GameEngine) -> dict[str, dict[str, int]]:
        return {
            player.private_goal.id: {
                condition.metric: int(condition.value)
                for condition in player.private_goal.conditions
            }
            for player in engine.state.players.values()
        }

    short_goals = conditions_by_goal(short)
    long_goals = conditions_by_goal(long)
    assert short_goals["engineer_repair"] == {"repair_count": 1, "world.energy": 25}
    assert long_goals["engineer_repair"] == {"repair_count": 4, "world.energy": 7}
    assert short_goals["doctor_survival"]["world.medicine"] == 8
    assert long_goals["doctor_survival"]["world.medicine"] == 1
    assert short_goals["trader_deals"]["trades_completed"] == 1
    assert long_goals["trader_deals"]["trades_completed"] == 5
    assert short_goals["researcher_analysis"] == {
        "events_analyzed": 1,
        "craft_count": 1,
    }
    assert long_goals["researcher_analysis"] == {
        "events_analyzed": 5,
        "craft_count": 4,
    }
