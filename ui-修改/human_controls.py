from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from game.actions import SECRET_ACTIONS
from game.enums import ActionType, GamePhase, ProposalStatus, TradeStatus
from game.exceptions import GameRuleError
from ui.chat import render_chat_history
from ui.session import GameSession


ACTION_LABELS = {
    "explore": "探索外部区域",
    "repair": "修理设施",
    "investigate": "调查",
    "heal": "治疗重伤",
    "craft": "制造物资",
    "sabotage": "秘密破坏",
    "steal": "秘密偷窃",
    "search": "搜索资源",
    "transfer_resource": "转移个人资源",
    "minor_heal": "简单治疗",
    "reinforce": "加固设施",
    "protect": "保护目标",
    "rest": "休息",
    "persuade": "拉拢合作",
    "spread_rumor": "制造谣言",
}

RESOURCE_NAMES = {
    "food": "食物",
    "energy": "能源",
    "medicine": "药品",
    "parts": "零件",
}

TARGET_NAMES = {
    "nearby_ruins": "附近废墟",
    "old_station": "旧车站",
    "surface_camp": "地表营地",
    "storage": "仓库",
    "workshop": "工坊",
    "medical_room": "医疗室",
    "repair_kit": "维修工具包",
    "analysis_kit": "分析工具包",
    "medical_kit": "医疗包",
}

PHASE_HINTS = {
    GamePhase.EVENT: "先阅读今日事件。事件阶段不能执行正式行动。",
    GamePhase.DISCUSSION: "可以发言、提出方案、私聊或交易，完成后进入行动阶段。",
    GamePhase.ACTION: "你有有限行动点，可以执行行动或职业技能，也可以提前结束。",
    GamePhase.VOTING: "对公共方案投票，完成后进入结算阶段。",
    GamePhase.RESOLUTION: "查看本日结果，然后进入下一阶段。",
    GamePhase.EXPULSION: "完成提名、辩护和驱逐投票，然后进入下一天。",
    GamePhase.FINISHED: "本局已经结束，可前往赛后复盘查看完整结果。",
}


def _format_resources(resources: dict[str, int]) -> str:
    if not resources:
        return "无资源要求"
    return " · ".join(
        f"{RESOURCE_NAMES.get(name, name)} × {amount}" for name, amount in resources.items()
    )


def _format_target(session: GameSession, target: str) -> str:
    state = session.engine.state
    if target in state.players:
        return state.players[target].name
    if target in state.facilities:
        return state.facilities[target].name
    if state.current_event and target == state.current_event.id:
        return state.current_event.title
    return TARGET_NAMES.get(target, target)


def _run(
    label: str,
    action: Callable[[], Any],
    *,
    success_message: str | None = None,
) -> None:
    try:
        action()
        st.session_state.notice = ("success", success_message or f"{label}成功")
    except (GameRuleError, ValueError) as exc:
        st.session_state.notice = ("error", str(exc))
    st.rerun()


def _send_private_chat(session: GameSession, receiver_id: str, content: str) -> None:
    try:
        replied = session.send_private_message(receiver_id, content)
        message = "私聊已发送，AI 已回复。" if replied else "私聊已发送，但 AI 当前无法回复。"
        st.session_state.notice = ("success", message)
    except (GameRuleError, ValueError) as exc:
        st.session_state.notice = ("error", str(exc))
    st.rerun()


def _player_options(session: GameSession, include_self: bool = False) -> list[str]:
    human_id = session.human.player_id
    return [
        player.id
        for player in session.engine.state.players.values()
        if player.is_present and (include_self or player.id != human_id)
    ]


def _advance_stage(session: GameSession, label: str, *, end_turn: bool = False) -> None:
    def advance() -> None:
        if end_turn and not session.engine.state.players[session.human.player_id].ended_turn:
            session.human.end_turn()
        session.advance_once()

    _run(label, advance)


def render_human_controls(session: GameSession) -> None:
    phase = session.engine.state.phase
    st.markdown("### 本阶段操作")
    st.caption(PHASE_HINTS[phase])
    if phase == GamePhase.DISCUSSION:
        _render_discussion(session)
    elif phase == GamePhase.ACTION:
        _render_actions(session)
    elif phase == GamePhase.VOTING:
        _render_voting(session)
    elif phase == GamePhase.EXPULSION:
        _render_expulsion(session)
    elif phase == GamePhase.EVENT:
        st.info("当前只能查看事件，点击下方按钮后进入讨论阶段。", icon=":material/info:")
        if st.button(
            "查看事件并进入讨论",
            key="human_event_continue",
            type="primary",
            width="stretch",
            icon=":material/arrow_forward:",
        ):
            _advance_stage(session, "进入讨论")
    elif phase == GamePhase.RESOLUTION:
        st.info("系统将在推进时结算资源、事件和公开行动。", icon=":material/calculate:")
        if st.button(
            "结算本日并继续",
            key="human_resolution_continue",
            type="primary",
            width="stretch",
            icon=":material/arrow_forward:",
        ):
            _advance_stage(session, "完成结算")
    else:
        st.success("本局已经结束，请打开“赛后复盘”查看结果。")


def _render_discussion(session: GameSession) -> None:
    human = session.human
    engine = session.engine
    proposal, private, trade = st.tabs(["公共方案", "私聊", "交易"])
    with proposal:
        event = engine.state.current_event
        if event:
            st.caption(f"当前事件：{event.title} · 规则成本：{_format_resources(event.resource_cost)}")
            with st.form("human_proposal"):
                title = st.text_input("方案标题", value=f"处理：{event.title}")
                solution = st.selectbox("建议方案", event.available_solutions)
                if st.form_submit_button("提交公共方案", width="stretch"):
                    payload = {
                        "title": title,
                        "description": solution,
                        "resource_cost": dict(event.resource_cost),
                        "participants": [human.player_id],
                        "target_event": event.id,
                    }
                    _run("提交方案", lambda: human.propose(payload))
    with private:
        targets = _player_options(session)
        if targets:
            receiver = st.selectbox(
                "私聊对象",
                targets,
                format_func=lambda pid: engine.state.players[pid].name,
                key="private_chat_receiver",
            )
            conversation = [
                item
                for item in engine.get_recent_messages(human.player_id, 60)
                if item["receiver_id"]
                and {item["sender_id"], item["receiver_id"]}
                == {human.player_id, receiver}
            ]
            render_chat_history(
                session,
                conversation,
                empty_text=f"你和 {engine.state.players[receiver].name} 还没有私聊记录。",
                height=360,
            )
            limit_reached = engine.state.players[human.player_id].private_chats_today >= 1
            if content := st.chat_input(
                "今日私聊次数已用完"
                if limit_reached
                else f"私信 {engine.state.players[receiver].name}……",
                key=f"private_chat_input_{receiver}",
                max_chars=500,
                disabled=limit_reached,
                submit_mode="disable",
            ):
                _send_private_chat(session, receiver, content)
            if limit_reached:
                st.caption("每天最多主动私聊 1 次，AI 回复不会占用你的次数。")
        else:
            st.caption("当前没有可私聊的玩家。")
    with trade:
        targets = _player_options(session)
        resources = ["food", "medicine", "parts", "energy"]
        if targets:
            with st.form("human_trade"):
                receiver = st.selectbox("交易对象", targets, format_func=lambda pid: engine.state.players[pid].name)
                c1, c2 = st.columns(2)
                with c1:
                    offer_resource = st.selectbox(
                        "我提供", resources, format_func=lambda name: RESOURCE_NAMES[name]
                    )
                    offer_amount = st.number_input("提供数量", 1, 10, 1)
                with c2:
                    request_resource = st.selectbox(
                        "我请求", resources, index=2, format_func=lambda name: RESOURCE_NAMES[name]
                    )
                    request_amount = st.number_input("请求数量", 0, 10, 1)
                promise = st.text_input("附带承诺（可选）")
                if st.form_submit_button("发起交易", width="stretch"):
                    request = {request_resource: int(request_amount)} if request_amount else {}
                    _run(
                        "发起交易",
                        lambda: engine.propose_trade(
                            human.player_id,
                            receiver,
                            {offer_resource: int(offer_amount)},
                            request,
                            promise=promise or None,
                        ),
                    )
        incoming = [
            item
            for item in engine.state.trades.values()
            if item.receiver_id == human.player_id and item.status == TradeStatus.PENDING
        ]
        for item in incoming:
            with st.container(border=True):
                st.markdown(f"**来自 {engine.state.players[item.sender_id].name} 的交易**")
                st.caption(
                    f"对方提供：{_format_resources(item.offer)} ｜ 希望获得：{_format_resources(item.request)}"
                )
                if item.promise:
                    st.markdown(f"承诺：{item.promise}")
                with st.container(horizontal=True):
                    if st.button("接受", key=f"accept_{item.id}"):
                        _run(
                            "接受交易",
                            lambda item_id=item.id: engine.accept_trade(human.player_id, item_id),
                        )
                    if st.button("拒绝", key=f"reject_{item.id}"):
                        _run(
                            "拒绝交易",
                            lambda item_id=item.id: engine.reject_trade(human.player_id, item_id),
                        )

    if st.button(
        "完成讨论并进入行动",
        key="human_discussion_continue",
        type="primary",
        width="stretch",
        icon=":material/arrow_forward:",
    ):
        _advance_stage(session, "进入行动")


def _render_actions(session: GameSession) -> None:
    human = session.human
    engine = session.engine
    available = engine.get_available_actions(human.player_id)
    if not available:
        st.warning("当前没有合法行动。")
        if st.button(
            "结束行动并进入投票",
            key="human_no_action_continue",
            type="primary",
            width="stretch",
            icon=":material/arrow_forward:",
        ):
            _advance_stage(session, "进入投票", end_turn=True)
        return
    cost_by_type = {item["type"]: item["ap_cost"] for item in available}
    action_type = st.selectbox(
        "选择行动",
        list(cost_by_type),
        format_func=lambda name: f"{ACTION_LABELS.get(name, name)} · {cost_by_type[name]} AP",
        key="human_action_type",
    )
    payload: dict[str, Any] = {"type": action_type}
    facilities = list(engine.state.facilities)
    other_players = _player_options(session)
    all_players = _player_options(session, include_self=True)
    if action_type in {"repair", "reinforce", "sabotage"}:
        payload["target"] = st.selectbox(
            "目标设施", facilities, format_func=lambda target: _format_target(session, target)
        )
    elif action_type == "protect":
        targets = facilities + other_players
        payload["target"] = st.selectbox(
            "保护目标",
            targets,
            format_func=lambda target: _format_target(session, target),
        )
    elif action_type == "investigate":
        targets = other_players + facilities
        if engine.state.current_event:
            targets.append(engine.state.current_event.id)
        payload["target"] = st.selectbox(
            "调查目标", targets, format_func=lambda target: _format_target(session, target)
        )
    elif action_type in {"heal", "minor_heal"}:
        payload["target"] = st.selectbox(
            "治疗对象", all_players, format_func=lambda pid: engine.state.players[pid].name
        )
    elif action_type in {"persuade", "spread_rumor"}:
        payload["target"] = st.selectbox(
            "目标玩家", other_players, format_func=lambda pid: engine.state.players[pid].name
        )
    elif action_type == "transfer_resource":
        payload["target"] = st.selectbox(
            "接收玩家", other_players, format_func=lambda pid: engine.state.players[pid].name
        )
        payload["resource"] = st.selectbox(
            "个人资源",
            ["food", "medicine", "parts", "energy"],
            format_func=lambda name: RESOURCE_NAMES[name],
        )
        payload["amount"] = st.number_input("数量", 1, 10, 1)
    elif action_type == "steal":
        payload["resource"] = st.selectbox(
            "偷窃资源",
            ["food", "energy", "medicine", "parts"],
            format_func=lambda name: RESOURCE_NAMES[name],
        )
    elif action_type == "explore":
        payload["target"] = st.selectbox(
            "探索区域",
            ["nearby_ruins", "old_station", "surface_camp"],
            format_func=lambda target: TARGET_NAMES[target],
        )
    elif action_type == "search":
        payload["target"] = st.selectbox(
            "搜索地点",
            ["storage", "workshop", "medical_room"],
            format_func=lambda target: TARGET_NAMES[target],
        )
    elif action_type == "craft":
        payload["target"] = st.selectbox(
            "制造物品",
            ["repair_kit", "analysis_kit", "medical_kit"],
            format_func=lambda target: TARGET_NAMES[target],
        )

    if st.button(
        "执行行动",
        key="perform_human_action",
        width="stretch",
        type="primary",
        icon=":material/play_arrow:",
    ):
        kind = ActionType(action_type)
        if kind in SECRET_ACTIONS:
            _run(
                "秘密行动",
                lambda: human.secret_act(payload),
                success_message="秘密行动已提交，将在结算阶段生效。",
            )
        else:
            _run(
                "行动",
                lambda: human.act(payload),
                success_message="行动已提交，将在结算阶段获得结果。",
            )
    player = engine.state.players[human.player_id]
    skill_by_role = {
        "Engineer": ("emergency_repair", "紧急抢修"),
        "Doctor": ("full_diagnosis", "全面诊疗"),
        "Guard": ("secret_monitoring", "秘密监控"),
        "Trader": ("resource_exchange", "资源置换"),
        "Researcher": ("risk_forecast", "风险预测"),
    }
    skill, skill_label = skill_by_role[player.public_role.value]
    with st.expander(f"职业技能：{skill_label}"):
        if player.public_role.value == "Engineer":
            skill_target = st.selectbox(
                "抢修设施",
                facilities,
                key="skill_engineer_target",
                format_func=lambda target: _format_target(session, target),
            )
        elif player.public_role.value in {"Doctor", "Guard"}:
            skill_target = st.selectbox(
                "技能目标",
                all_players,
                format_func=lambda pid: engine.state.players[pid].name,
                key="skill_player_target",
            )
        elif player.public_role.value == "Trader":
            skill_target = st.selectbox(
                "目标资源",
                ["food", "energy", "medicine", "parts"],
                key="skill_trade_target",
                format_func=lambda name: RESOURCE_NAMES[name],
            )
        else:
            skill_target = None
            st.caption("获得下一天事件的模糊风险提示。")
        cooldown = player.cooldowns.get(skill, 0)
        st.caption(f"当前冷却：{cooldown} 天 · 使用技能需要 1 AP")
        if st.button("使用职业技能", key="use_profession_skill", disabled=cooldown > 0):
            _run("使用技能", lambda: human.use_skill(skill, skill_target))

    if st.button(
        "结束行动并进入投票",
        key="human_action_continue",
        type="primary",
        width="stretch",
        icon=":material/arrow_forward:",
    ):
        _advance_stage(session, "进入投票", end_turn=True)


def _render_voting(session: GameSession) -> None:
    human = session.human
    proposals = [
        item
        for item in session.engine.state.proposals.values()
        if item.created_day == session.engine.state.day and item.status == ProposalStatus.PENDING
    ]
    if not proposals:
        st.info("当前没有待投票方案。")
    else:
        for item in proposals:
            existing_vote = item.votes.get(human.player_id)
            card_state = "submitted" if existing_vote else "pending"
            card_key = f"vote_card_{card_state}_{item.id.replace('-', '_')}"
            with st.container(border=True, key=card_key):
                st.markdown(f"**{item.title}**")
                proposer = session.engine.state.players[item.proposer_id].name
                st.caption(f"成本：{_format_resources(item.resource_cost)} · 提案人：{proposer}")
                if existing_vote:
                    vote_label = {
                        "support": "支持",
                        "oppose": "反对",
                        "abstain": "弃权",
                    }[existing_vote.value]
                    st.success(
                        f"你的投票已提交：{vote_label}",
                        icon=":material/how_to_vote:",
                    )
                    st.caption("投票已锁定；卡片保留并置灰，不可重复提交。")
                else:
                    choice = st.segmented_control(
                        "你的选择",
                        ["support", "oppose", "abstain"],
                        format_func=lambda value: {
                            "support": "支持",
                            "oppose": "反对",
                            "abstain": "弃权",
                        }[value],
                        default="abstain",
                        key=f"vote_choice_{item.id}",
                    )
                    if st.button("提交投票", key=f"vote_submit_{item.id}"):
                        _run(
                            "投票",
                            lambda item_id=item.id, vote_choice=choice: human.vote(
                                item_id, vote_choice
                            ),
                        )

    if st.button(
        "完成投票并进入结算",
        key="human_voting_continue",
        type="primary",
        width="stretch",
        icon=":material/arrow_forward:",
    ):
        _advance_stage(session, "进入结算")


def _render_expulsion(session: GameSession) -> None:
    human = session.human
    engine = session.engine
    case = engine.state.expulsion
    if not case or not case.target_id:
        targets = _player_options(session)
        if not targets:
            st.info("没有可提名玩家。")
        else:
            target = st.selectbox(
                "提名驱逐", targets, format_func=lambda pid: engine.state.players[pid].name
            )
            if st.button("提交提名", key="human_nominate"):
                _run("驱逐提名", lambda: human.nominate(target))
        if st.button(
            "结束驱逐流程并进入下一天",
            key="human_expulsion_continue_empty",
            type="primary",
            width="stretch",
            icon=":material/arrow_forward:",
        ):
            _advance_stage(session, "完成驱逐阶段")
        return
    target = engine.state.players[case.target_id]
    st.warning(f"联合提名目标：{target.name}（身份不会立即公开）")
    if case.target_id == human.player_id and case.defense is None:
        defense = st.text_area("公开辩护")
        if st.button("提交辩护"):
            _run("提交辩护", lambda: human.defend(defense))
    if human.player_id not in case.votes:
        yes, no = st.columns(2)
        if yes.button("赞成驱逐", width="stretch"):
            _run("驱逐投票", lambda: human.vote_expulsion(True))
        if no.button("反对驱逐", width="stretch"):
            _run("驱逐投票", lambda: human.vote_expulsion(False))

    if st.button(
        "结束驱逐流程并进入下一天",
        key="human_expulsion_continue",
        type="primary",
        width="stretch",
        icon=":material/arrow_forward:",
    ):
        _advance_stage(session, "完成驱逐阶段")
