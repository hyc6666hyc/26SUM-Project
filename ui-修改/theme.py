from __future__ import annotations

import streamlit as st


CSS = r"""
<style>
:root {
  --bg: #071014;
  --panel: rgba(12, 25, 31, .88);
  --panel-soft: rgba(16, 34, 42, .72);
  --line: rgba(104, 180, 199, .20);
  --cyan: #39d5f6;
  --amber: #e7a740;
  --text: #eef6f8;
  --muted: #8da7ae;
  --danger: #ef6a67;
}
html, body, [data-testid="stAppViewContainer"] {
  background:
    radial-gradient(circle at 15% 10%, rgba(29, 115, 134, .20), transparent 32%),
    radial-gradient(circle at 88% 12%, rgba(140, 87, 24, .16), transparent 30%),
    linear-gradient(150deg, #050a0d 0%, #09151a 52%, #05090c 100%);
  color: var(--text);
}
/* 隐藏菜单和页脚，但保留侧边栏开关所在的页头 */
#MainMenu,
footer {
  display: none !important;
}

/* 页头透明，不影响游戏界面 */
[data-testid="stHeader"] {
  background: transparent !important;
}

/* 确保侧边栏收起后，重新打开按钮仍然可见 */
[data-testid="stSidebarCollapsedControl"] {
  display: flex !important;
  visibility: visible !important;
}
[data-testid="stMainBlockContainer"] { max-width: 1480px; padding-top: 1.2rem; }
[data-testid="stSidebar"] {
  background: rgba(5, 14, 18, .96);
  border-right: 1px solid var(--line);
}
.sc-nav {
  display: flex; align-items: center; gap: .8rem; min-height: 3rem;
  font-weight: 800; letter-spacing: .08em; font-size: 1.25rem;
}
.sc-logo {
  width: 2.3rem; height: 2.3rem; display: grid; place-items: center;
  border: 1px solid rgba(231,167,64,.75); color: var(--amber);
  border-radius: .65rem; background: rgba(231,167,64,.08);
}
.sc-hero { text-align: center; padding: 4.4rem 0 2.6rem; }
.sc-hero h1 {
  margin: 0; font-size: clamp(3.2rem, 7vw, 6.5rem); line-height: 1;
  letter-spacing: .12em; color: #f4f6f5;
  text-shadow: 0 0 35px rgba(57,213,246,.12);
}
.sc-hero .subtitle { color: var(--cyan); font-size: 1.25rem; letter-spacing: .2em; margin-top: 1.25rem; }
.sc-hero .tagline { color: #dfbd83; letter-spacing: .12em; margin-top: 1.5rem; }
.sc-card-title { font-size: 1.65rem; font-weight: 800; margin-bottom: .25rem; }
.sc-card-copy { min-height: 3.2rem; color: var(--muted); }
.sc-chip {
  display: inline-block; padding: .22rem .65rem; border: 1px solid var(--line);
  border-radius: 999px; margin: .25rem .25rem .4rem 0; color: #b9d7de; font-size: .82rem;
}
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--panel); border-color: var(--line) !important;
  box-shadow: 0 14px 40px rgba(0,0,0,.22); border-radius: 1rem;
}
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
  border: 1px solid rgba(57,213,246,.35); background: rgba(20, 55, 65, .72);
  color: var(--text); border-radius: .65rem; font-weight: 700;
}
.stButton > button:hover, .stFormSubmitButton > button:hover {
  border-color: var(--cyan); color: white; box-shadow: 0 0 18px rgba(57,213,246,.16);
}
[data-testid="stMetric"] {
  background: var(--panel-soft); border: 1px solid var(--line); border-radius: .8rem; padding: .75rem;
}
[data-testid="stMetricValue"] { color: #eef9fb; }
[class*="st-key-vote_card_submitted_"] {
  opacity: .52;
  filter: saturate(.45);
  transition: opacity .2s ease, filter .2s ease;
}
[class*="st-key-vote_card_submitted_"] [data-testid="stVerticalBlockBorderWrapper"] {
  box-shadow: none;
}
.sc-status {
  display: inline-flex; align-items: center; gap: .4rem; padding: .3rem .7rem;
  border: 1px solid var(--line); border-radius: 999px; color: #bad3d9; font-size: .85rem;
}
.sc-phase {
  display: inline-block; padding: .32rem .75rem; border-radius: 999px;
  background: rgba(231,167,64,.12); border: 1px solid rgba(231,167,64,.36); color: #f0c476;
}
.sc-event {
  background: linear-gradient(135deg, rgba(32,57,65,.72), rgba(19,30,36,.9));
  border-left: 4px solid var(--amber); border-radius: .8rem; padding: 1.1rem 1.2rem;
}
.sc-event h3 { margin: 0 0 .35rem; }
.sc-muted { color: var(--muted); }
.sc-player {
  border: 1px solid rgba(104,180,199,.14); background: rgba(18,34,40,.55);
  border-radius: .65rem; padding: .55rem .65rem; margin-bottom: .45rem;
}
.sc-log {
  padding: .55rem .7rem; border-left: 2px solid rgba(57,213,246,.32);
  background: rgba(12,27,33,.55); margin-bottom: .4rem; border-radius: 0 .45rem .45rem 0;
}
.sc-footer { text-align: center; color: #68848b; padding: 2.2rem 0 1rem; font-size: .8rem; }
div[data-baseweb="tab-list"] { gap: .35rem; }
button[data-baseweb="tab"] { background: rgba(16,34,42,.55); border-radius: .55rem; }
</style>
"""


def apply_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
