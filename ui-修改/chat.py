from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import streamlit as st

from ui.session import GameSession


def render_chat_history(
    session: GameSession,
    messages: Sequence[dict[str, Any]],
    *,
    empty_text: str,
    height: int = 380,
) -> None:
    """Render permission-filtered engine messages as a scrollable chat history."""
    human_id = session.human.player_id if session.human else None
    with st.container(height=height, border=True):
        if not messages:
            st.caption(empty_text)
            return
        for item in messages:
            is_human = item["sender_id"] == human_id
            sender = session.engine.state.players[item["sender_id"]].name
            receiver_id = item.get("receiver_id")
            with st.chat_message(
                "user" if is_human else "assistant",
                avatar=":material/person:" if is_human else ":material/smart_toy:",
            ):
                if receiver_id:
                    receiver = session.engine.state.players[receiver_id].name
                    st.caption(f"{sender} → {receiver}")
                else:
                    st.caption(sender)
                st.markdown(item["content"])
