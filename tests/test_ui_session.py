from __future__ import annotations

from game.enums import GamePhase
from ui.session import build_game_session


def test_ai_ui_session_advances_one_phase() -> None:
    session = build_game_session(mode="ai", player_count=3, total_days=1, random_seed=7)
    assert session.mode == "ai"
    assert session.human is None
    assert session.engine.state.phase == GamePhase.EVENT
    session.advance_once()
    assert session.engine.state.phase == GamePhase.DISCUSSION


def test_human_ui_session_binds_private_view() -> None:
    session = build_game_session(mode="human", player_count=3, total_days=1, random_seed=8)
    assert session.human is not None
    view = session.human.view()
    assert view["private"]["player_id"] == "player_1"
    assert session.viewer_id == "player_1"


def test_human_private_message_gets_one_ai_reply() -> None:
    session = build_game_session(mode="human", player_count=3, total_days=1, random_seed=9)
    session.advance_once()
    assert session.engine.state.phase == GamePhase.DISCUSSION

    replied = session.send_private_message("player_2", "你愿意支持这个方案吗？")
    messages = session.engine.get_recent_messages("player_1", 20)

    assert replied is True
    assert any(
        item["sender_id"] == "player_2"
        and item["receiver_id"] == "player_1"
        for item in messages
    )


def test_human_public_message_triggers_bounded_ai_discussion() -> None:
    session = build_game_session(mode="human", player_count=3, total_days=1, random_seed=10)
    session.advance_once()

    response_count = session.send_public_message("大家先讨论今天的事件。")
    public_messages = [
        item
        for item in session.engine.get_recent_messages("player_1", 20)
        if not item["receiver_id"]
    ]

    assert response_count == 2
    assert len(public_messages) == 3
