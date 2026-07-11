from __future__ import annotations

import streamlit as st

from game.rules import scaled_saboteur_targets


def _configured_total_days() -> int:
    if st.session_state.get("page") == "game" and "game_session" in st.session_state:
        return int(st.session_state.game_session.engine.config.total_days)
    return int(st.session_state.get("setup_days", 6))


@st.dialog("游戏规则", width="large", icon="📖")
def show_rules() -> None:
    """Rules modal shared by the landing page and active match page."""
    total_days = _configured_total_days()
    sabotage_count, facility_limit = scaled_saboteur_targets(total_days)
    overview, flow, identity, victory = st.tabs(
        ["核心目标", "每日流程", "身份与驱逐", "胜负条件"]
    )
    with overview:
        st.markdown(
            f"""
            ### 在 {total_days} 天内让避难所存活

            - 公共资源包括食物、能源、药品、零件和稳定度。
            - 每名玩家拥有公开职业、私人目标和关系记忆。
            - 私人目标的次数和数值会按对局天数自动调整。
            - 健康玩家每天有 **2 AP**；受伤玩家只有 **1 AP**。
            - 数值、合法性、随机结果与秘密权限全部由规则引擎处理。
            """
        )
    with flow:
        st.markdown(
            """
            1. **事件 EVENT**：公布当天危机与可选方案。
            2. **讨论 DISCUSSION**：公开发言、私聊、提案与交易。
            3. **行动 ACTION**：修理、探索、治疗、调查或执行秘密行动。
            4. **投票 VOTING**：方案须获得有效玩家严格过半支持。
            5. **结算 RESOLUTION**：执行方案和行动，扣除每日资源。
            6. **驱逐 EXPULSION**：每两天可联合提名并秘密投票。
            """
        )
    with identity:
        st.markdown(
            """
            ### 普通阵营与隐藏破坏者

            普通玩家要兼顾公共生存和私人目标。破坏者会伪装成普通职业，
            可以秘密破坏设施、偷窃资源或制造谣言。秘密行动的公共日志不会显示执行者。
            秘密行动会留下私有线索；重复破坏会让线索更明确，并提高其他玩家的怀疑度。

            驱逐需要至少两名有效玩家联合提名，随后严格过半赞成才会成功。
            被驱逐者的真实身份只在游戏结束后公开；误驱逐普通玩家会令稳定度 **-8**。
            """
        )
    with victory:
        st.markdown(
            f"""
            ### 避难所存活

            第 {total_days} 天结算后，稳定度必须大于 0，食物与能源不能同时归零，
            至少三名玩家仍在场，并且至少两个核心设施没有完全失效。

            ### 立即崩溃

            稳定度归零、食物或能源连续两天归零、在场玩家少于两人，
            或四个核心设施全部失效，都会让游戏提前结束。

            ### 阵营胜负互斥

            普通阵营需要让避难所存活，并阻止破坏者完成阵营目标。
            本局破坏者需要使避难所崩溃、使稳定度低于 25，或至少完成 {sabotage_count} 次秘密干扰且把任一核心设施降至 {facility_limit}% 或以下。
            破坏者仅完成普通的个人积累，不再能获得阵营胜利。
            """
        )
    st.caption("提示：进入游戏后，页面右上角仍可随时打开本规则窗口。")
