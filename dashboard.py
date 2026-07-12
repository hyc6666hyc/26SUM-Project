from __future__ import annotations

import html
import time
from pathlib import Path

import streamlit as st

from game.enums import GamePhase
from game.exceptions import GameRuleError
from services.storage import JSONStorage
from ui.chat import render_chat_history
from ui.human_controls import ACTION_LABELS, TARGET_NAMES, render_human_controls
from ui.layout import render_top_nav
from ui.session import GameSession


PHASE_NAMES = {
    GamePhase.EVENT: "事件",
    GamePhase.DISCUSSION: "讨论",
    GamePhase.ACTION: "行动",
    GamePhase.VOTING: "投票",
    GamePhase.RESOLUTION: "结算",
    GamePhase.EXPULSION: "驱逐",
    GamePhase.FINISHED: "已结束",
}

ROLE_NAMES = {
    "Engineer": "工程师",
    "Doctor": "医生",
    "Guard": "警卫",
    "Trader": "商人",
    "Researcher": "研究员",
}

HEALTH_NAMES = {
    "HEALTHY": "健康",
    "INJURED": "受伤",
    "SERIOUSLY_INJURED": "重伤",
    "UNCONSCIOUS": "昏迷",
    "ISOLATED": "隔离",
    "EXPELLED": "已驱逐",
    "DEAD": "死亡",
}

RESOURCE_NAMES = {
    "food": "食物",
    "energy": "能源",
    "medicine": "药品",
    "parts": "零件",
    "stability": "稳定度",
}

FACTION_NAMES = {
    "SURVIVOR": "普通阵营",
    "SABOTEUR": "隐藏破坏者",
    "SURVIVORS": "幸存者阵营",
    "SABOTEUR_PARTIAL": "破坏者部分胜利",
}

PHASE_FLOW = [
    GamePhase.EVENT,
    GamePhase.DISCUSSION,
    GamePhase.ACTION,
    GamePhase.VOTING,
    GamePhase.RESOLUTION,
    GamePhase.EXPULSION,
]

PERSONALITY_NAMES = {
    "cooperation": "合作倾向",
    "risk_tolerance": "风险偏好",
    "selfishness": "利己倾向",
    "deception": "欺骗倾向",
    "suspicion": "警惕程度",
    "obedience": "服从倾向",
    "leadership": "领导倾向",
    "revenge": "报复倾向",
}

STATUS_NAMES = {
    "pending": "待处理",
    "queued": "待结算",
    "resolved": "已结算",
    "executed": "已执行",
    "passed": "已通过",
    "failed": "未通过",
    "accepted": "已接受",
    "rejected": "已拒绝",
    "countered": "已还价",
    "cancelled": "已取消",
}

DISPLAY_TERMS = {
    "medicine": "药品",
    "energy": "能源",
    "food": "食物",
    "parts": "零件",
}


def _format_resources(resources: dict[str, int]) -> str:
    if not resources:
        return "无资源要求"
    return " · ".join(
        f"{RESOURCE_NAMES.get(name, name)} × {amount}" for name, amount in resources.items()
    )


def _player_name(session: GameSession, player_id: str | None) -> str:
    if not player_id:
        return "—"
    player = session.engine.state.players.get(player_id)
    return player.name if player else player_id


def _target_name(session: GameSession, target: str | None) -> str:
    if not target:
        return "—"
    state = session.engine.state
    if target in state.players:
        return state.players[target].name
    if target in state.facilities:
        return state.facilities[target].name
    if state.current_event and target == state.current_event.id:
        return state.current_event.title
    return TARGET_NAMES.get(target, target)


def _render_text_items(items: list[str], empty_text: str) -> None:
    if not items:
        st.caption(empty_text)
        return
    for item in items:
        with st.container(border=True):
            st.markdown(_humanize_text(item))


def _humanize_text(value: object) -> str:
    text = str(value)
    for source, target in DISPLAY_TERMS.items():
        text = text.replace(source, target)
    return text


def _notice() -> None:
    notice = st.session_state.pop("notice", None)
    if not notice:
        return
    level, message = notice
    getattr(st, level, st.info)(message)


def _advance(session: GameSession) -> None:
    try:
        with st.spinner("议会正在推进……"):
            session.advance_once()
        st.session_state.notice = ("success", "阶段已推进")
    except Exception as exc:
        session.auto_running = False
        st.session_state.notice = ("error", f"推进失败：{exc}")
    st.rerun()


def _send_public_chat(session: GameSession, content: str) -> None:
    try:
        response_count = session.send_public_message(content)
        message = (
            f"发言已发送，{response_count} 名 AI 已完成本阶段回应。"
            if response_count
            else "发言已发送。"
        )
        st.session_state.notice = ("success", message)
    except (GameRuleError, ValueError) as exc:
        st.session_state.notice = ("error", str(exc))
    st.rerun()


def _recommended_public_messages(session: GameSession) -> tuple[str, str, str]:
    state = session.engine.state
    event_title = state.current_event.title if state.current_event else "当前危机"
    weakest = min(state.facilities.values(), key=lambda item: item.durability)
    resources = state.resources
    return (
        f"我建议先讨论“{event_title}”的应对方案，确认成本后再投票。",
        f"当前食物 {resources.food}、能源 {resources.energy}，请优先保障公共资源安全线。",
        f"{weakest.name}耐久度只有 {weakest.durability}%，建议修理的同时调查异常损坏线索。",
    )


def _render_sidebar(session: GameSession) -> None:
    engine = session.engine
    state = engine.state
    with st.sidebar:
        st.subheader("游戏控制")
        mode_text = "AI 自动对局" if session.mode == "ai" else "真人参与模式"
        st.caption(mode_text)
        if session.llm_player_ids:
            st.success(f"LLM Agent：{len(session.llm_player_ids)} 名")
        else:
            st.info("规则 Bot 模式")

        if session.mode == "ai":
            if st.button(
                "单步推进",
                width="stretch",
                disabled=state.finished,
                icon=":material/skip_next:",
            ):
                _advance(session)
        else:
            st.caption("真人模式请使用主区域的阶段操作按钮推进流程。")

        if session.mode == "ai" and not state.finished:
            if session.auto_running:
                if st.button(
                    "暂停自动推进", width="stretch", icon=":material/pause:"
                ):
                    session.auto_running = False
                    st.rerun()
            else:
                if st.button(
                    "自动推进", width="stretch", icon=":material/play_arrow:"
                ):
                    session.auto_running = True
                    st.rerun()

        if st.button("保存当前对局", width="stretch", icon=":material/save:"):
            path = JSONStorage.save(engine, Path("data/saves/ui_latest_game.json"))
            st.session_state.notice = ("success", f"已保存：{path}")
            st.rerun()
        if st.button("返回开始页", width="stretch", icon=":material/arrow_back:"):
            st.session_state.page = "start"
            st.session_state.pop("game_session", None)
            st.rerun()

        st.divider()
        st.subheader("玩家列表")
        for player in state.players.values():
            marker = "你" if session.human and player.id == session.human.player_id else "AI"
            role = ROLE_NAMES.get(player.public_role.value, player.public_role.value)
            health = HEALTH_NAMES.get(player.health.value, player.health.value)
            st.markdown(
                (
                    '<div class="sc-player">'
                    f'<b>{html.escape(player.name)}</b> · {marker}<br>'
                    f'<span class="sc-muted">{role} · {health} · AP {player.ap}</span>'
                    "</div>"
                ),
                unsafe_allow_html=True,
            )


def _render_resources(session: GameSession) -> None:
    resources = session.engine.state.resources
    values = [
        ("食物", resources.food),
        ("能源", resources.energy),
        ("药品", resources.medicine),
        ("零件", resources.parts),
        ("稳定度", resources.stability),
    ]
    with st.container(horizontal=True):
        for label, value in values:
            st.metric(label, value, border=True)


def _render_phase_progress(session: GameSession) -> None:
    phase = session.engine.state.phase
    if phase == GamePhase.FINISHED:
        st.progress(1.0, text="本局流程已完成")
        return
    current = PHASE_FLOW.index(phase)
    labels = "  →  ".join(
        f"**{PHASE_NAMES[item]}**" if item == phase else PHASE_NAMES[item] for item in PHASE_FLOW
    )
    st.progress((current + 1) / len(PHASE_FLOW), text=f"今日流程 {current + 1}/{len(PHASE_FLOW)}")
    st.markdown(labels)
    if session.human and phase == GamePhase.EVENT:
        with st.container(border=True):
            st.markdown("**第一步：阅读今日事件**")
            st.caption("事件阶段不能直接行动。确认事件后，系统会进入讨论阶段。")
            if st.button(
                "查看事件并进入讨论",
                key="human_event_continue_top",
                type="primary",
                width="stretch",
                icon=":material/arrow_forward:",
            ):
                _advance(session)


def _render_event_and_facilities(session: GameSession) -> None:
    engine = session.engine
    event_col, facility_col = st.columns([1.65, 1], gap="large")
    with event_col:
        event = engine.state.current_event
        if event:
            solutions = " · ".join(event.available_solutions)
            st.markdown(
                (
                    '<div class="sc-event">'
                    f'<h3>今日事件：{html.escape(event.title)}</h3>'
                    f'<div>{html.escape(event.description)}</div>'
                    f'<div class="sc-muted" style="margin-top:.55rem">公开后果：{html.escape(event.visible_effect)}</div>'
                    f'<div class="sc-muted">可选应对：{html.escape(solutions)}</div>'
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
    with facility_col:
        st.markdown("#### 核心设施")
        for facility in engine.state.facilities.values():
            st.progress(
                facility.durability / 100,
                text=f"{facility.name} · {facility.durability}% · {facility.condition}",
            )


def _render_council(session: GameSession) -> None:
    engine = session.engine
    viewer = session.viewer_id
    message_col, proposal_col = st.columns([1.25, 1], gap="large")
    with message_col:
        st.markdown("#### 公共讨论")
        messages = [item for item in engine.get_recent_messages(viewer, 30) if not item["receiver_id"]]
        render_chat_history(
            session,
            messages[-16:],
            empty_text="议会尚未出现公开发言。",
            height=420,
        )
        if session.human:
            if engine.state.phase == GamePhase.DISCUSSION:
                human_player = engine.state.players[session.human.player_id]
                limit_reached = human_player.public_messages_today >= 2
                st.caption("推荐发言（点击即发送）")
                for index, suggestion in enumerate(_recommended_public_messages(session), start=1):
                    if st.button(
                        suggestion,
                        key=f"council_suggestion_{index}",
                        disabled=limit_reached,
                        width="stretch",
                    ):
                        _send_public_chat(session, suggestion)
                with st.expander("第 4 项：自定义发言"):
                    custom_content = st.text_area(
                        "编辑发言",
                        key="custom_council_message",
                        max_chars=500,
                        disabled=limit_reached,
                        placeholder="输入你想对议会说的内容……",
                    )
                    if st.button(
                        "发送自定义发言",
                        key="send_custom_council_message",
                        disabled=limit_reached,
                        type="primary",
                        width="stretch",
                    ):
                        _send_public_chat(session, custom_content)
                if limit_reached:
                    st.caption("每天最多公开发言 2 次。")
            else:
                st.caption("公共发言仅在讨论阶段开放。")
    with proposal_col:
        st.markdown("#### 公共方案")
        proposals = engine.view_proposals(viewer)
        if not proposals:
            st.caption("今天还没有公共方案。")
        for item in proposals:
            with st.container(border=True):
                status = STATUS_NAMES.get(item["status"], item["status"])
                st.markdown(f"**{item['title']}** · `{status}`")
                st.caption(item["description"])
                st.caption(f"资源成本：{_format_resources(item['resource_cost'])}")
                votes = list(item["votes"].values())
                if votes:
                    st.caption(
                        f"支持 {votes.count('support')} · 反对 {votes.count('oppose')} · 弃权 {votes.count('abstain')}"
                    )


def _render_private(session: GameSession) -> None:
    engine = session.engine
    if session.human:
        private = engine.get_private_state(session.human.player_id)
        faction = "隐藏破坏者" if private["hidden_faction"] == "SABOTEUR" else "普通阵营"
        player = engine.state.players[session.human.player_id]
        st.warning("以下内容仅对你可见。", icon=":material/visibility_lock:")
        overview, intelligence, relationships, records = st.tabs(
            ["身份与资源", "线索与记忆", "信任关系", "我的记录"]
        )

        with overview:
            with st.container(horizontal=True):
                st.metric("隐藏阵营", faction, border=True)
                st.metric(
                    "公开职业",
                    ROLE_NAMES.get(player.public_role.value, player.public_role.value),
                    border=True,
                )
                st.metric("当前 AP", player.ap, border=True)

            goal = private.get("private_goal")
            goal_title = "隐藏破坏目标" if private["hidden_faction"] == "SABOTEUR" else "私人目标"
            with st.container(border=True):
                st.markdown(f"#### {goal_title}")
                if goal:
                    status = "已完成" if goal["completed"] else "进行中"
                    color = "green" if goal["completed"] else "orange"
                    st.badge(status, color=color)
                    st.markdown(_humanize_text(goal["description"]))
                else:
                    st.caption("当前没有私人目标。")

            with st.container(border=True):
                st.markdown("#### 当前计划")
                st.markdown(_humanize_text(private["current_plan"] or "尚未制定计划。"))

            st.markdown("#### 个人资源")
            with st.container(horizontal=True):
                for name in ("food", "energy", "medicine", "parts"):
                    st.metric(
                        RESOURCE_NAMES[name],
                        private["personal_resources"].get(name, 0),
                        border=True,
                    )
            pending_actions = [
                item for item in private["action_records"] if item["status"] == "queued"
            ]
            if pending_actions:
                st.caption(
                    f"有 {len(pending_actions)} 项行动等待结算；探索所得会在结算阶段加入个人资源。"
                )

            if private["inventory"]:
                st.markdown("#### 随身物品")
                inventory_rows = [
                    {"物品": name, "数量": amount}
                    for name, amount in private["inventory"].items()
                ]
                st.dataframe(inventory_rows, hide_index=True, width="stretch")

            if private["personality"]:
                with st.expander("性格画像", icon=":material/psychology:"):
                    personality_rows = [
                        {"倾向": PERSONALITY_NAMES.get(name, name), "强度": value}
                        for name, value in private["personality"].items()
                    ]
                    st.dataframe(
                        personality_rows,
                        hide_index=True,
                        width="stretch",
                        column_config={
                            "强度": st.column_config.ProgressColumn(
                                "强度", min_value=0, max_value=100
                            )
                        },
                    )

        with intelligence:
            st.markdown("#### 已获得线索")
            _render_text_items(private["clues"], "暂无线索。")

            memory_col, promise_col = st.columns(2)
            with memory_col:
                st.markdown("#### 本回合记忆")
                _render_text_items(private["turn_memory"], "本回合暂无关键记忆。")
                st.markdown("#### 整局关键记忆")
                _render_text_items(private["key_memory"], "暂无长期记忆。")
            with promise_col:
                st.markdown("#### 承诺记录")
                _render_text_items(private["promises"], "暂无承诺。")
                st.markdown("#### 技能冷却")
                cooldown_rows = [
                    {"技能": name, "剩余天数": days}
                    for name, days in private["cooldowns"].items()
                ]
                if cooldown_rows:
                    st.dataframe(cooldown_rows, hide_index=True, width="stretch")
                else:
                    st.caption("暂无冷却中的技能。")

            st.markdown("#### 私聊记录")
            private_messages = [
                item
                for item in engine.get_recent_messages(session.human.player_id, 30)
                if item["receiver_id"]
            ]
            render_chat_history(
                session,
                private_messages,
                empty_text="暂无私聊记录。",
                height=320,
            )

        with relationships:
            relation_rows = []
            for other_id, relation in engine.get_relationships(session.human.player_id).items():
                relation_rows.append(
                    {
                        "玩家": _player_name(session, other_id),
                        "信任": relation["trust"],
                        "怀疑": relation["suspicion"],
                        "合作": relation["cooperation"],
                        "诚实": relation["honesty"],
                        "作用": relation["usefulness"],
                        "已知承诺": len(relation["known_promises"]),
                        "违约": len(relation["broken_promises"]),
                    }
                )
            st.dataframe(
                relation_rows,
                hide_index=True,
                width="stretch",
                column_config={
                    name: st.column_config.ProgressColumn(name, min_value=0, max_value=100)
                    for name in ("信任", "怀疑", "合作", "诚实", "作用")
                },
            )

        with records:
            st.markdown("#### 行动记录")
            action_rows = [
                {
                    "天数": item["day"],
                    "行动": ACTION_LABELS.get(item["type"], item["type"]),
                    "目标": _target_name(session, item["target"]),
                    "状态": STATUS_NAMES.get(item["status"], item["status"]),
                    "结果": item["result"] or "等待结算",
                }
                for item in private["action_records"]
            ]
            if action_rows:
                st.dataframe(action_rows, hide_index=True, width="stretch")
            else:
                st.caption("暂无行动记录。")

            st.markdown("#### 投票记录")
            vote_rows = []
            for item in private["vote_records"]:
                proposal = engine.state.proposals.get(item["proposal_id"])
                vote_rows.append(
                    {
                        "方案": proposal.title if proposal else item["proposal_id"],
                        "选择": {"support": "支持", "oppose": "反对", "abstain": "弃权"}.get(
                            item["choice"], item["choice"]
                        ),
                        "结果": STATUS_NAMES.get(item["status"], item["status"]),
                    }
                )
            if vote_rows:
                st.dataframe(vote_rows, hide_index=True, width="stretch")
            else:
                st.caption("暂无投票记录。")

            st.markdown("#### 交易记录")
            trade_rows = [
                {
                    "交易对象": _player_name(
                        session,
                        item["receiver_id"]
                        if item["sender_id"] == session.human.player_id
                        else item["sender_id"],
                    ),
                    "提供": _format_resources(item["offer"]),
                    "请求": _format_resources(item["request"]),
                    "承诺": item["promise"] or "—",
                    "状态": STATUS_NAMES.get(item["status"], item["status"]),
                }
                for item in private["trade_records"]
            ]
            if trade_rows:
                st.dataframe(trade_rows, hide_index=True, width="stretch")
            else:
                st.caption("暂无交易记录。")
    else:
        st.warning("管理员观察模式属于调试视图，会显示身份与秘密行动。", icon=":material/bug_report:")
        if st.toggle("开启管理员观察", key="admin_observer"):
            admin = engine.get_admin_state()
            identity_rows = [
                {
                    "玩家": _player_name(session, player_id),
                    "真实阵营": FACTION_NAMES.get(faction, faction),
                }
                for player_id, faction in admin["identities"].items()
            ]
            st.markdown("#### 完整身份")
            st.dataframe(identity_rows, hide_index=True, width="stretch")

            st.markdown("#### 当前隐藏风险")
            st.warning(admin["hidden_event_risk"] or "当前事件没有额外隐藏风险。")

            st.markdown("#### 已结算秘密行动")
            secret_rows = [
                {
                    "执行者": _player_name(session, item["player_id"]),
                    "行动": ACTION_LABELS.get(item["type"], item["type"]),
                    "目标": _target_name(session, item["target"]),
                    "结果": item["result"] or "—",
                }
                for item in admin["secret_actions"]
            ]
            if secret_rows:
                st.dataframe(secret_rows, hide_index=True, width="stretch")
            else:
                st.caption("暂无已结算秘密行动。")

            with st.expander("管理员日志", icon=":material/description:"):
                if not admin["admin_logs"]:
                    st.caption("暂无管理员日志。")
                for item in admin["admin_logs"]:
                    st.markdown(
                        f'<div class="sc-log"><b>第 {item["day"]} 天 · {item["phase"]}</b><br>'
                        f'{html.escape(item["message"])}</div>',
                        unsafe_allow_html=True,
                    )
        else:
            st.info("保持关闭时只展示公共信息。")


def _render_logs(session: GameSession) -> None:
    logs = session.engine.get_visible_logs(session.viewer_id, 80)
    if not logs:
        st.caption("暂无日志。")
        return
    day_filter = st.selectbox("按天筛选", ["全部"] + list(range(1, session.engine.state.day + 1)))
    for item in logs:
        if day_filter != "全部" and item["day"] != day_filter:
            continue
        st.markdown(
            (
                '<div class="sc-log">'
                f'<b>第 {item["day"]} 天 · {item["phase"]} · {item["category"]}</b><br>'
                f'{html.escape(item["message"])}'
                "</div>"
            ),
            unsafe_allow_html=True,
        )


def _render_review(session: GameSession) -> None:
    result = session.engine.state.result
    if not result:
        st.info("游戏结束后，这里将显示阵营结果、个人目标、积分、关键投票和秘密行动。")
        return
    st.success(f"阵营结果：{FACTION_NAMES.get(result.faction_winner, result.faction_winner)}")
    with st.container(horizontal=True):
        st.metric(
            "避难所",
            "成功存活" if result.shelter_survived else "已经崩溃",
            border=True,
        )
        st.metric("崩溃原因", result.collapse_reason or "无", border=True)

    player_rows = []
    for player_id, item in result.player_results.items():
        player_rows.append(
            {
                "玩家": item["name"],
                "最终阵营": FACTION_NAMES.get(item["faction"], item["faction"]),
                "个人结果": item["outcome"],
                "个人/阵营目标": "已完成" if item["private_goal_completed"] else "未完成",
                "积分": item["score"],
                "策略摘要": item["strategy_summary"],
            }
        )
    player_rows.sort(key=lambda item: item["积分"], reverse=True)
    st.markdown("#### 玩家结果")
    st.dataframe(player_rows, hide_index=True, width="stretch")

    summary = result.summary
    with st.container(horizontal=True):
        st.metric(
            "最有影响力",
            _player_name(session, summary.get("most_influential")),
            border=True,
        )
        st.metric(
            "最受信任",
            _player_name(session, summary.get("most_trusted")),
            border=True,
        )
        st.metric(
            "最受怀疑",
            _player_name(session, summary.get("most_suspicious")),
            border=True,
        )
        st.metric(
            "驱逐判断",
            "正确" if summary.get("expulsion_correct") else "未驱逐破坏者",
            border=True,
        )

    review_tabs = st.tabs(["关键公开信息", "秘密行动", "承诺与交易"])
    with review_tabs[0]:
        st.markdown("#### 关键发言")
        _render_text_items(summary.get("key_public_messages", []), "暂无关键公开发言。")
        st.markdown("#### 投票与驱逐")
        _render_text_items(
            summary.get("key_vote_and_expulsion_results", []),
            "暂无关键投票或驱逐记录。",
        )
    with review_tabs[1]:
        secret_rows = [
            {
                "执行者": _player_name(session, item["actor_id"]),
                "行动": ACTION_LABELS.get(item["type"], item["type"]),
                "目标": _target_name(session, item["target"]),
                "结果": item["result"] or "—",
            }
            for item in summary.get("revealed_secret_actions", [])
        ]
        if secret_rows:
            st.dataframe(secret_rows, hide_index=True, width="stretch")
        else:
            st.caption("本局没有已公开的秘密行动。")
    with review_tabs[2]:
        st.markdown("#### 公开交易")
        _render_text_items(summary.get("public_trades", []), "暂无公开交易。")
        st.markdown("#### 承诺记录")
        promise_rows = []
        for player_id, promises in summary.get("promises", {}).items():
            promise_rows.append(
                {
                    "玩家": _player_name(session, player_id),
                    "作出承诺": "；".join(promises["made"]) or "无",
                    "已知违约": "；".join(promises["known_broken"]) or "无",
                }
            )
        if promise_rows:
            st.dataframe(promise_rows, hide_index=True, width="stretch")
        else:
            st.caption("暂无承诺记录。")


def _render_llm_stats(session: GameSession) -> None:
    stats = session.llm_client.stats.as_dict()
    st.markdown("#### LLM 调用概览")
    with st.container(horizontal=True):
        st.metric("决策数", stats["decisions"], border=True)
        st.metric("请求数", stats["requests"], border=True)
        st.metric("成功", stats["successful_decisions"], border=True)
        st.metric("失败", stats["failed_decisions"], border=True)
    with st.container(horizontal=True):
        st.metric("输入 tokens", stats["prompt_tokens"], border=True)
        st.metric("输出 tokens", stats["completion_tokens"], border=True)
        st.metric("总 tokens", stats["total_tokens"], border=True)
        st.metric("总耗时", f"{stats['total_seconds']:.2f} 秒", border=True)
    model_rows = [
        {"模型": model, "请求次数": count}
        for model, count in stats["model_requests"].items()
    ]
    if model_rows:
        st.dataframe(model_rows, hide_index=True, width="stretch")


def render_dashboard() -> None:
    session: GameSession = st.session_state.game_session
    engine = session.engine
    render_top_nav("game")
    _render_sidebar(session)
    _notice()

    title_col, status_col = st.columns([3, 1], vertical_alignment="center")
    with title_col:
        st.title(f"第 {engine.state.day} 天 · {PHASE_NAMES[engine.state.phase]}阶段")
    with status_col:
        if engine.state.finished:
            st.error("对局已结束")
        elif session.auto_running:
            st.success("自动推进中")
        else:
            st.info("等待指令")

    _render_resources(session)
    _render_phase_progress(session)
    dashboard_tabs = ["议会大厅", "行动与投票", "私人状态", "日志回放", "赛后复盘"]
    council, controls, private, logs, review = st.tabs(dashboard_tabs)
    with council:
        _render_event_and_facilities(session)
        st.space("small")
        _render_council(session)

    with controls:
        if session.human:
            render_human_controls(session)
        else:
            st.info("AI 模式由左侧的“单步推进”或“自动推进”控制。")
            if session.llm_client:
                _render_llm_stats(session)

    with private:
        _render_private(session)

    with logs:
        _render_logs(session)

    with review:
        _render_review(session)
    

    st.markdown('<div class="sc-footer">游戏规则按钮在对局期间始终位于页面右上角</div>', unsafe_allow_html=True)

    if session.auto_running and not engine.state.finished:
        time.sleep(engine.config.auto_advance_delay)
        session.advance_once()
        st.rerun()
