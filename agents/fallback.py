from __future__ import annotations

from agents.schemas import ActionChoice, AgentDecision, ProposalChoice
from game.actions import action_ap_cost
from game.engine import GameEngine
from game.enums import ActionType, Faction, GamePhase, HealthStatus, Role


class RuleBasedBot:
    """Finite deterministic fallback policy used without an API key or after errors."""

    def decide(self, engine: GameEngine, player_id: str) -> AgentDecision:
        state = engine.state
        player = state.players[player_id]
        decision = AgentDecision(strategy_summary="规则型保底策略")
        if not player.is_present:
            return decision

        if state.phase == GamePhase.DISCUSSION:
            if player.can_speak and player.public_messages_today < 2:
                decision.public_message = self._discussion_message(engine, player_id)
            todays = [item for item in state.proposals.values() if item.created_day == state.day]
            event = state.current_event
            if (
                event
                and not todays
                and player.proposals_today < 1
                and state.resources.can_afford(event.resource_cost)
            ):
                decision.proposal = ProposalChoice(
                    title=f"处理：{event.title}",
                    description=f"采用规则方案应对{event.title}，优先保证避难所生存。",
                    resource_cost=dict(event.resource_cost),
                    participants=[player_id],
                    target_event=event.id,
                )
        elif state.phase == GamePhase.ACTION:
            decision.actions = self._choose_actions(engine, player_id)
        elif state.phase == GamePhase.VOTING:
            sabotage_start_day = 1 if state.config.total_days <= 3 else 2
            for proposal in state.proposals.values():
                if proposal.created_day == state.day:
                    affordable = state.resources.can_afford(proposal.resource_cost)
                    decision.votes[proposal.id] = (
                        "oppose"
                        if player.hidden_faction == Faction.SABOTEUR
                        and state.day >= sabotage_start_day
                        else "support"
                        if affordable
                        else "oppose"
                    )
        elif state.phase == GamePhase.EXPULSION:
            case = state.expulsion
            if case and case.target_id:
                if case.target_id == player_id and case.defense is None:
                    decision.defense = "我的公开行动有记录可查，请根据证据而不是猜测投票。"
                if player.can_vote and player_id not in case.votes:
                    decision.expulsion_vote = state.day >= 4
            elif player.can_vote:
                candidates = [
                    other
                    for other in state.players.values()
                    if other.id != player_id and other.is_present
                ]
                if candidates:
                    candidates.sort(
                        key=lambda other: (
                            -player.relationships[other.id].suspicion,
                            other.id,
                        )
                    )
                    decision.expulsion_nomination = candidates[0].id
                    # If this nomination forms the joint target, the same bounded
                    # decision may also submit a vote without a second agent call.
                    decision.expulsion_vote = state.day >= 4
        return decision

    def private_reply(
        self,
        engine: GameEngine,
        player_id: str,
        sender_id: str,
        content: str,
    ) -> str:
        """Return one short, displayable reply without starting another agent turn."""
        player = engine.state.players[player_id]
        relation = player.relationships[sender_id]
        if relation.suspicion >= 60:
            opening = "收到，但我会先核实相关信息"
        elif relation.cooperation >= 60 or relation.trust >= 60:
            opening = "收到，我愿意配合"
        else:
            opening = "收到，我会认真考虑"

        if any(word in content for word in ("卧底", "破坏", "怀疑", "线索")):
            detail = "我会结合行动记录和线索判断，不会只凭猜测下结论。"
        elif any(word in content for word in ("投票", "支持", "反对", "方案")):
            detail = "投票时我会重点检查资源成本和对避难所的实际收益。"
        elif any(word in content for word in ("交易", "资源", "食物", "药品", "零件", "能源")):
            detail = "如果需要交换资源，请在交易页给出明确的提供和请求。"
        else:
            role_focus = {
                Role.ENGINEER: "我会优先关注受损设施和维修需求。",
                Role.DOCTOR: "我会优先关注伤员、药品和生存风险。",
                Role.GUARD: "我会关注异常行动和可能留下的线索。",
                Role.TRADER: "我会比较资源消耗与方案收益。",
                Role.RESEARCHER: "我会先评估当前事件的隐藏风险。",
            }
            detail = role_focus[player.public_role]
        return f"{opening}。{detail}"

    @staticmethod
    def _discussion_message(engine: GameEngine, player_id: str) -> str:
        event = engine.state.current_event
        resources = engine.state.resources
        if resources.food < 10 or resources.energy < 10:
            return "公共资源已经接近警戒线，我建议先保证食物和能源。"
        return f"我建议优先处理“{event.title}”，并控制资源成本。" if event else "请优先保证公共生存。"

    def _choose_actions(self, engine: GameEngine, player_id: str) -> list[ActionChoice]:
        state = engine.state
        player = state.players[player_id]
        if player.ap <= 0 or not player.can_act:
            return []
        if player.health == HealthStatus.INJURED:
            return [ActionChoice(type="rest")]

        sabotage_start_day = 1 if state.config.total_days <= 3 else 2
        if player.hidden_faction == Faction.SABOTEUR and state.day >= sabotage_start_day:
            target = min(state.facilities.values(), key=lambda facility: facility.durability).id
            if player.ap >= 2 and player.secret_actions_today == 0:
                return [ActionChoice(type="sabotage", target=target, secret=True)]

        weakest = min(state.facilities.values(), key=lambda facility: facility.durability)
        if (
            player.public_role == Role.ENGINEER
            and weakest.durability < 80
            and state.resources.parts >= 2
        ):
            actions = [ActionChoice(type="repair", target=weakest.id)]
            remaining = player.ap - action_ap_cost(player, ActionType.REPAIR)
            if remaining >= 1:
                actions.append(ActionChoice(type="search", target="storage"))
            return actions
        if player.public_role == Role.DOCTOR and state.resources.medicine >= 2:
            patients = [
                item
                for item in state.players.values()
                if item.is_present and item.health in {HealthStatus.INJURED, HealthStatus.SERIOUSLY_INJURED}
            ]
            if patients:
                return [ActionChoice(type="heal", target=patients[0].id)]
        if player.public_role == Role.GUARD and weakest.durability < 65:
            return [ActionChoice(type="protect", target=weakest.id)]
        if player.public_role == Role.RESEARCHER and state.resources.parts >= 1:
            return [ActionChoice(type="craft", target="analysis_kit")]
        if state.resources.food < 12 or state.resources.energy < 10:
            return [ActionChoice(type="explore", target="nearby_ruins")]
        return [
            ActionChoice(type="search", target="storage"),
            ActionChoice(type="search", target="workshop"),
        ][: player.ap]
