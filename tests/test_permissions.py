from __future__ import annotations

import json

import pytest

from agents.llm_agent import LLMAgent
from agents.schemas import AgentDecision
from game.exceptions import GameRuleError
from game.views import PlayerView
from services.llm_client import LLMClient


def test_public_and_bound_view_do_not_expose_other_private_goals(engine) -> None:
    view = PlayerView(engine, "player_1")
    public_text = json.dumps(view.public_state(), ensure_ascii=False)
    own_private = view.private_state()
    other_goal = engine.state.players["player_2"].private_goal.description
    assert "private_goal" not in public_text
    assert own_private["player_id"] == "player_1"
    assert other_goal not in json.dumps(own_private, ensure_ascii=False)


def test_private_message_visible_only_to_both_parties(engine) -> None:
    engine.advance_phase()
    secret = "只给二号的承诺"
    engine.send_private_message("player_1", "player_2", secret)
    assert secret in json.dumps(engine.get_recent_messages("player_1"), ensure_ascii=False)
    assert secret in json.dumps(engine.get_recent_messages("player_2"), ensure_ascii=False)
    assert secret not in json.dumps(engine.get_recent_messages("player_3"), ensure_ascii=False)


def test_blank_public_message_is_rejected_cleanly(engine) -> None:
    engine.advance_phase()
    with pytest.raises(GameRuleError, match="发言长度"):
        engine.send_public_message("player_1", "   ")


def test_invalid_llm_json_uses_fallback(engine) -> None:
    calls = []

    def broken_transport(messages, model, timeout):
        calls.append(messages)
        return "not-json"

    engine.advance_phase()  # discussion
    agent = LLMAgent(LLMClient(transport=broken_transport))
    decision = agent.decide(engine, "player_1")
    assert decision.strategy_summary == "规则型保底策略"
    assert decision.public_message
    assert len(calls) == 2  # original + one repair only
    assert agent.client.stats.decisions == 1
    assert agent.client.stats.requests == 2
    assert agent.client.stats.format_repairs == 1
    assert agent.client.stats.failed_decisions == 1


def test_llm_prompt_contains_no_other_players_private_goal(engine) -> None:
    captured = []

    def capture(messages, model, timeout):
        captured.append(json.dumps(messages, ensure_ascii=False))
        return "not-json"

    engine.advance_phase()
    LLMAgent(LLMClient(transport=capture)).decide(engine, "player_1")
    other_goal = engine.state.players["player_2"].private_goal.description
    assert all(other_goal not in item for item in captured)


def test_authentication_error_is_not_retried() -> None:
    class UnauthorizedError(RuntimeError):
        status_code = 401

    calls = 0

    def unauthorized_transport(messages, model, timeout):
        nonlocal calls
        calls += 1
        raise UnauthorizedError("invalid key")

    client = LLMClient(transport=unauthorized_transport, max_retries=1)
    result = client.generate_structured(
        [{"role": "user", "content": "return JSON"}], AgentDecision, "test-model"
    )
    assert result is None
    assert calls == 1
    assert client.stats.requests == 1
    assert client.stats.api_errors == 1
    assert client.stats.failed_decisions == 1
