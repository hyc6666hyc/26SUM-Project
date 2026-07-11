from __future__ import annotations

import streamlit as st

from ui.dashboard import render_dashboard
from ui.start import render_start_page
from ui.theme import apply_theme


st.set_page_config(
    page_title="避难所议会",
    page_icon="⌂",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()
st.session_state.setdefault("page", "start")

if st.session_state.page == "game" and "game_session" in st.session_state:
    render_dashboard()
else:
    render_start_page()
