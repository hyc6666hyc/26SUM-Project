from __future__ import annotations

import streamlit as st

from ui.rules import show_rules


PHASE_NAMES = {
    "EVENT": "事件",
    "DISCUSSION": "讨论",
    "ACTION": "行动",
    "VOTING": "投票",
    "RESOLUTION": "结算",
    "EXPULSION": "驱逐",
    "FINISHED": "已结束",
}


def render_top_nav(context: str) -> None:
    left, center, right = st.columns([4, 3, 1.25], vertical_alignment="center")
    with left:
        st.markdown(
            '<div class="sc-nav"><span class="sc-logo">⌂</span><span>避难所议会</span></div>',
            unsafe_allow_html=True,
        )
    with center:
        if context == "game" and "game_session" in st.session_state:
            session = st.session_state.game_session
            state = session.engine.state
            phase = PHASE_NAMES.get(state.phase.value, state.phase.value)
            st.markdown(
                f'<div style="text-align:right"><span class="sc-phase">第 {state.day} 天 · {phase}</span></div>',
                unsafe_allow_html=True,
            )
    with right:
        if st.button(
            "游戏规则",
            key=f"rules_{context}",
            width="stretch",
            icon=":material/menu_book:",
        ):
            show_rules()
