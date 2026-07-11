from __future__ import annotations

from pathlib import Path

import pytest


streamlit = pytest.importorskip("streamlit")
from streamlit.proto.TextInput_pb2 import TextInput


def test_streamlit_start_and_ai_dashboard() -> None:
    from streamlit.testing.v1 import AppTest

    app_path = Path(__file__).resolve().parent.parent / "app.py"
    app = AppTest.from_file(app_path, default_timeout=10).run()
    assert not app.exception
    labels = [button.label for button in app.button]
    assert "游戏规则" in labels
    assert "开始 AI 对局" in labels
    assert "加入避难所" in labels
    app.slider(key="setup_days").set_value(2).run()
    assert any(
        "2 天局" in item.value and "干扰 1 次" in item.value
        for item in app.caption
    )

    app.toggle(key="setup_use_llm").set_value(True).run()
    assert app.text_input(key="setup_llm_api_key").proto.type == TextInput.PASSWORD
    assert app.text_input(key="setup_llm_base_url")
    assert app.text_input(key="setup_llm_model")

    app.toggle(key="setup_use_llm").set_value(False).run()
    app.button(key="start_ai").click().run()
    assert not app.exception
    dashboard_labels = [button.label for button in app.button]
    assert "游戏规则" in dashboard_labels
    assert "单步推进" in dashboard_labels


def test_human_can_reach_action_stage_from_main_page() -> None:
    from streamlit.testing.v1 import AppTest

    app_path = Path(__file__).resolve().parent.parent / "app.py"
    app = AppTest.from_file(app_path, default_timeout=10).run()
    app.button(key="start_human").click().run()

    assert not app.exception
    assert "单步推进" not in [button.label for button in app.button]
    assert app.button(key="human_event_continue_top").label == "查看事件并进入讨论"

    app.button(key="human_event_continue_top").click().run()
    assert not app.exception
    assert [app.button(key=f"council_suggestion_{index}") for index in range(1, 4)]
    assert app.text_area(key="custom_council_message")
    assert app.button(key="send_custom_council_message").label == "发送自定义发言"
    assert not any(button.key == "human_discussion_continue" for button in app.button)

    app.session_state["dashboard_tab"] = "行动与投票"
    app.run()
    assert app.button(key="human_discussion_continue").label == "完成讨论并进入行动"
    assert not any(
        button.key and str(button.key).startswith("council_suggestion_")
        for button in app.button
    )
    session = app.session_state["game_session"]
    session.advance_once()
    app.session_state["dashboard_tab"] = "行动与投票"
    app.run()
    assert not app.exception
    assert app.selectbox(key="human_action_type")
    assert app.button(key="perform_human_action").label == "执行行动"


def test_submitted_vote_card_is_retained_and_marked_as_faded() -> None:
    from streamlit.testing.v1 import AppTest

    from ui.theme import CSS

    app_path = Path(__file__).resolve().parent.parent / "app.py"
    app = AppTest.from_file(app_path, default_timeout=10).run()
    app.button(key="start_human").click().run()
    app.button(key="human_event_continue_top").click().run()

    session = app.session_state["game_session"]
    event = session.engine.state.current_event
    proposal_id = session.human.propose(
        {
            "title": "保留投票卡片测试",
            "description": event.available_solutions[0],
            "resource_cost": dict(event.resource_cost),
            "participants": [session.human.player_id],
            "target_event": event.id,
        }
    )
    app.run()
    app.session_state["dashboard_tab"] = "行动与投票"
    app.run()
    session.advance_once()
    session.human.end_turn()
    session.advance_once()

    app.session_state["dashboard_tab"] = "行动与投票"
    app.run()
    assert app.button(key=f"vote_submit_{proposal_id}").label == "提交投票"
    session.human.vote(proposal_id, "support")

    app.session_state["dashboard_tab"] = "行动与投票"
    app.run()
    assert not app.exception
    assert any("你的投票已提交：支持" in item.value for item in app.success)
    assert "st-key-vote_card_submitted_" in CSS
