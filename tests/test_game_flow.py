from __future__ import annotations

from pathlib import Path

from agents.llm_agent import LLMAgent
from game.autoplay import run_auto_game
from game.autoplay import AutoGameRunner
from game.engine import GameEngine
from game.enums import GamePhase
from game.models import GameConfig
from services.llm_client import LLMClient
from services.storage import JSONStorage


def test_game_settles_after_day_six() -> None:
    engine = run_auto_game(GameEngine(GameConfig(total_days=6, random_seed=7)))
    assert engine.state.finished
    assert engine.state.day == 6
    assert engine.state.result is not None
    assert engine.state.result.revealed_identities


def test_auto_game_is_bounded() -> None:
    config = GameConfig(total_days=6, random_seed=9, max_steps=100)
    engine = run_auto_game(GameEngine(config))
    assert engine.state.finished
    assert engine.state.step_count <= config.max_steps


def test_non_decision_phases_do_not_call_agent() -> None:
    class CountingAgent:
        def __init__(self) -> None:
            self.calls = 0

        def decide(self, engine, player_id):
            from agents.schemas import AgentDecision

            self.calls += 1
            return AgentDecision(strategy_summary="count")

    engine = GameEngine(GameConfig(player_count=3, total_days=1, max_steps=30))
    agent = CountingAgent()
    runner = AutoGameRunner(engine, {"player_1": agent})
    assert runner.process_ai_players() == 0  # EVENT
    assert agent.calls == 0
    engine.state.phase = GamePhase.RESOLUTION
    assert runner.process_ai_players() == 0
    assert agent.calls == 0


def test_one_day_one_llm_smoke_uses_three_requests() -> None:
    def valid_transport(messages, model, timeout):
        return '{"strategy_summary":"smoke"}'

    config = GameConfig(player_count=3, total_days=1, random_seed=42, max_steps=30)
    engine = GameEngine(config)
    client = LLMClient(transport=valid_transport)
    runner = AutoGameRunner(engine, {"player_1": LLMAgent(client)})
    runner.run()
    assert engine.state.finished
    assert client.stats.decisions == 3
    assert client.stats.requests == 3
    assert client.stats.successful_decisions == 3
    assert client.stats.failed_decisions == 0


def test_json_save_and_reload() -> None:
    engine = GameEngine(GameConfig(random_seed=17))
    engine.advance_phase()
    path = Path("data/saves/test_roundtrip.json")
    try:
        JSONStorage.save(engine, path)
        loaded = JSONStorage.load(path)
        assert loaded.state.day == engine.state.day
        assert loaded.state.phase == engine.state.phase
        assert loaded.event_order == engine.event_order
        assert loaded.get_private_state("player_1") == engine.get_private_state("player_1")
    finally:
        path.unlink(missing_ok=True)
