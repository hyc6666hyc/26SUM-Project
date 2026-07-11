from __future__ import annotations

import streamlit as st

from game.rules import scaled_saboteur_targets
from services.llm_client import LLMClient
from ui.layout import render_top_nav
from ui.session import build_game_session


def _init_start_defaults() -> None:
    defaults = {
        "setup_players": 6,
        "setup_days": 6,
        "setup_seed": 42,
        "setup_saboteur": True,
        "setup_use_llm": False,
        "setup_llm_agents": 1,
        "setup_llm_api_key": "",
        "setup_llm_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "setup_llm_model": "qwen3.6-flash",
        "setup_delay": 0.8,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _start_game(mode: str) -> None:
    try:
        session = build_game_session(
            mode=mode,
            player_count=int(st.session_state.setup_players),
            total_days=int(st.session_state.setup_days),
            random_seed=int(st.session_state.setup_seed),
            enable_saboteur=bool(st.session_state.setup_saboteur),
            use_llm=bool(st.session_state.setup_use_llm),
            llm_agents=int(st.session_state.setup_llm_agents),
            llm_api_key=str(st.session_state.setup_llm_api_key),
            llm_base_url=str(st.session_state.setup_llm_base_url),
            llm_model=str(st.session_state.setup_llm_model),
            auto_advance_delay=float(st.session_state.setup_delay),
        )
    except ValueError as exc:
        st.session_state.start_error = str(exc)
        return
    st.session_state.game_session = session
    st.session_state.page = "game"
    st.session_state.dashboard_tab = "议会大厅"
    st.session_state.notice = None
    st.rerun()


def render_start_page() -> None:
    _init_start_defaults()
    render_top_nav("start")
    st.markdown(
        """
        <section class="sc-hero">
          <h1>避难所议会</h1>
          <div class="subtitle">多智能体生存与社会博弈模拟系统</div>
          <div class="tagline">在资源耗尽之前，决定信任谁。</div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if error := st.session_state.pop("start_error", None):
        st.error(error)

    ai_col, human_col = st.columns(2, gap="large")
    with ai_col:
        with st.container(border=True):
            st.markdown('<div class="sc-card-title" style="color:#39d5f6">◉ AI 自动对局</div>', unsafe_allow_html=True)
            st.markdown(f"**{int(st.session_state.setup_players)} 名 AI Agent**")
            st.markdown('<div class="sc-card-copy">观察智能体讨论、交易、投票与生存博弈</div>', unsafe_allow_html=True)
            st.markdown('<span class="sc-chip">自动推进</span><span class="sc-chip">管理员观察</span>', unsafe_allow_html=True)
            if st.button(
                "开始 AI 对局",
                key="start_ai",
                width="stretch",
                type="primary",
                icon=":material/smart_toy:",
            ):
                _start_game("ai")
    with human_col:
        with st.container(border=True):
            st.markdown('<div class="sc-card-title" style="color:#e7a740">◉ 真人参与模式</div>', unsafe_allow_html=True)
            ai_count = max(2, int(st.session_state.setup_players) - 1)
            st.markdown(f"**1 名真人 + {ai_count} 名 AI**")
            st.markdown('<div class="sc-card-copy">你将获得私人目标，并与 AI 共同决策</div>', unsafe_allow_html=True)
            st.markdown('<span class="sc-chip">隐藏身份</span><span class="sc-chip">私人视图</span>', unsafe_allow_html=True)
            if st.button(
                "加入避难所",
                key="start_human",
                width="stretch",
                icon=":material/person:",
            ):
                _start_game("human")

    with st.expander("⚙ 高级设置", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.slider("玩家数量", 3, 8, key="setup_players")
        with c2:
            st.slider("游戏天数", 1, 10, key="setup_days")
            sabotage_count, facility_limit = scaled_saboteur_targets(
                int(st.session_state.setup_days)
            )
            st.caption(
                f"{int(st.session_state.setup_days)} 天局：次数型目标自动缩放；"
                f"破坏者需干扰 {sabotage_count} 次并将设施降至 {facility_limit}% 或以下。"
            )
        with c3:
            st.number_input("随机种子", min_value=0, max_value=999999, step=1, key="setup_seed")
        with c4:
            st.slider("自动推进间隔（秒）", 0.2, 3.0, step=0.2, key="setup_delay")
        x1, x2, x3 = st.columns(3)
        with x1:
            st.toggle("启用隐藏破坏者", key="setup_saboteur")
        with x2:
            st.toggle("使用 LLM", key="setup_use_llm")
        with x3:
            st.session_state.setup_llm_agents = min(
                int(st.session_state.setup_llm_agents),
                max(1, int(st.session_state.setup_players)),
            )
            st.slider(
                "LLM Agent 数量",
                1,
                max(1, int(st.session_state.setup_players)),
                key="setup_llm_agents",
                disabled=not st.session_state.setup_use_llm,
            )
        if st.session_state.setup_use_llm:
            st.markdown("##### LLM 连接")
            key_col, url_col, model_col = st.columns(3)
            with key_col:
                st.text_input(
                    "API Key",
                    key="setup_llm_api_key",
                    type="password",
                    autocomplete="off",
                    help="仅保存在当前浏览器会话，不写入存档或配置文件。",
                    icon=":material/key:",
                )
            with url_col:
                st.text_input(
                    "Base URL",
                    key="setup_llm_base_url",
                    placeholder="https://api.example.com/v1",
                    help="填写 OpenAI 兼容接口的 HTTPS Base URL。",
                    icon=":material/link:",
                )
            with model_col:
                st.text_input(
                    "模型名称",
                    key="setup_llm_model",
                    placeholder="例如 qwen3.6-flash",
                    help="必须是该接口账号可访问的模型 ID。",
                    icon=":material/model_training:",
                )
            if str(st.session_state.setup_llm_api_key).strip():
                st.success("将使用你输入的 API 配置，仅对当前会话生效。")
            elif LLMClient().available:
                st.success("未输入个人 Key，将使用服务器已配置的 LLM API。")
            else:
                st.warning("请填写 API Key、Base URL 和模型名称。")
            st.caption("仅支持 OpenAI 兼容的 HTTPS 接口；请确认服务商的模型 ID 和计费规则。")

    api_ready = bool(str(st.session_state.setup_llm_api_key).strip()) or LLMClient().available
    status_cols = st.columns([1, 1, 1])
    with status_cols[0]:
        st.markdown('<div class="sc-status">● 规则引擎就绪</div>', unsafe_allow_html=True)
    with status_cols[1]:
        text = "LLM API 已配置" if api_ready else "规则 Bot 可离线运行"
        st.markdown(f'<div class="sc-status">● {text}</div>', unsafe_allow_html=True)
    with status_cols[2]:
        st.markdown('<div class="sc-status">MVP v1.0</div>', unsafe_allow_html=True)
    st.markdown('<div class="sc-footer">SHELTER COUNCIL · DETERMINISTIC RULE ENGINE</div>', unsafe_allow_html=True)
