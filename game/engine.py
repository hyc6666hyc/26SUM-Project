from __future__ import annotations

import json
import math
import random
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from game.actions import SECRET_ACTIONS, action_ap_cost, available_action_types, validate_action
from game.enums import (
    ActionStatus,
    ActionType,
    Faction,
    GamePhase,
    HealthStatus,
    ProposalStatus,
    Role,
    TradeStatus,
    Visibility,
    VoteChoice,
)
from game.events import load_events
from game.exceptions import GameRuleError
from game.expulsion import expulsion_passed, nominated_target
from game.models import (
    Action,
    Event,
    ExpulsionCase,
    Facility,
    GameConfig,
    GameResult,
    GameState,
    GoalCondition,
    LogEntry,
    Message,
    Player,
    PrivateGoal,
    Proposal,
    Relationship,
    Trade,
)
from game.rules import (
    active_players,
    apply_structured_effect,
    collapse_reason,
    evaluate_private_goal,
    improve_health,
    describe_scaled_goal,
    scale_goal_conditions,
    shelter_survived,
    voting_players,
)
from game.scoring import player_score
from game.review import build_postgame_review
from game.voting import resolve_vote


class GameEngine:
    """Deterministic backend for a complete Shelter Council match."""

    def __init__(self, config: GameConfig | None = None, events: list[Event] | None = None) -> None:
        self.config = config or GameConfig()
        self.rng = random.Random(self.config.random_seed)
        self._counters: dict[str, int] = {}
        self._event_deck = list(events or load_events())
        self.rng.shuffle(self._event_deck)
        self.event_order = [event.id for event in self._event_deck]
        self._event_index = 0
        self._protections: dict[str, str] = {}
        self.state = GameState(config=self.config, facilities=self._initial_facilities())
        self._create_players()
        self._draw_event()

    @staticmethod
    def _initial_facilities() -> dict[str, Facility]:
        return {
            "water_system": Facility("water_system", "供水系统", 85),
            "power_system": Facility("power_system", "发电系统", 85),
            "medical_system": Facility("medical_system", "医疗系统", 80),
            "communication_system": Facility("communication_system", "通信系统", 75),
        }

    def _next_id(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}-{self._counters[prefix]:04d}"

    def _load_goals(self) -> dict[str, list[dict[str, Any]]]:
        path = Path(__file__).resolve().parent.parent / "data" / "goals.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def _make_goal(self, key: str, goals: dict[str, list[dict[str, Any]]]) -> PrivateGoal:
        item = self.rng.choice(goals[key])
        base_conditions = [GoalCondition(**condition) for condition in item["conditions"]]
        conditions = scale_goal_conditions(
            item["id"],
            base_conditions,
            total_days=self.config.total_days,
            player_count=self.config.player_count,
            enable_saboteur=self.config.enable_saboteur,
        )
        description = describe_scaled_goal(item["id"], conditions, item["description"])
        return PrivateGoal(item["id"], description, conditions)

    def _create_players(self) -> None:
        roles = list(Role)
        public_roles = [roles[index % len(roles)] for index in range(self.config.player_count)]
        self.rng.shuffle(public_roles)
        saboteur_index = (
            self.rng.randrange(self.config.player_count) if self.config.enable_saboteur else None
        )
        goals = self._load_goals()

        for index in range(self.config.player_count):
            player_id = f"player_{index + 1}"
            faction = Faction.SABOTEUR if index == saboteur_index else Faction.SURVIVOR
            role = public_roles[index]
            goal_key = "SABOTEUR" if faction == Faction.SABOTEUR else role.value
            personality = {
                name: self.rng.randint(25, 80)
                for name in (
                    "cooperation",
                    "risk_tolerance",
                    "selfishness",
                    "deception",
                    "suspicion",
                    "obedience",
                    "leadership",
                    "revenge",
                )
            }
            self.state.players[player_id] = Player(
                id=player_id,
                name=f"玩家{index + 1}",
                public_role=role,
                hidden_faction=faction,
                is_human=index < self.config.human_count,
                private_goal=self._make_goal(goal_key, goals),
                personality=personality,
                metrics={
                    "repair_count": 0,
                    "heal_count": 0,
                    "craft_count": 0,
                    "events_analyzed": 0,
                    "trades_completed": 0,
                    "prevented_sabotage": 0,
                    "voted_true_saboteur": 0,
                    "sabotage_count": 0,
                    "lowest_sabotaged_facility_durability": 100,
                    "proposals_passed": 0,
                },
            )

        for player in self.state.players.values():
            player.relationships = {
                other.id: Relationship()
                for other in self.state.players.values()
                if other.id != player.id
            }

    def _draw_event(self) -> Event:
        if self._event_index >= len(self._event_deck):
            self.rng.shuffle(self._event_deck)
            self._event_index = 0
        event = self._event_deck[self._event_index]
        self._event_index += 1
        self.state.current_event = event
        self.state.handled_event = False
        self._log(
            "event",
            f"第 {self.state.day} 天事件：{event.title}。{event.visible_effect}",
            data={"event_id": event.id},
        )
        return event

    def _log(
        self,
        category: str,
        message: str,
        visibility: Visibility = Visibility.PUBLIC,
        player_ids: Iterable[str] = (),
        data: dict[str, Any] | None = None,
    ) -> LogEntry:
        entry = LogEntry(
            id=self._next_id("log"),
            day=self.state.day,
            phase=self.state.phase,
            category=category,
            message=message,
            visibility=visibility,
            player_ids=list(player_ids),
            data=data or {},
        )
        self.state.logs.append(entry)
        return entry

    def _player(self, player_id: str) -> Player:
        try:
            return self.state.players[player_id]
        except KeyError as exc:
            raise GameRuleError(f"未知玩家: {player_id}", "UNKNOWN_PLAYER") from exc

    def _require_phase(self, *phases: GamePhase) -> None:
        if self.state.phase not in phases:
            expected = "/".join(phase.value for phase in phases)
            raise GameRuleError(
                f"当前阶段为 {self.state.phase.value}，该操作仅允许在 {expected}", "WRONG_PHASE"
            )

    # ------------------------------------------------------------------
    # Permission-filtered views
    # ------------------------------------------------------------------
    def get_public_state(self, player_id: str) -> dict[str, Any]:
        self._player(player_id)
        event = self.state.current_event
        players: list[dict[str, Any]] = []
        for player in self.state.players.values():
            item: dict[str, Any] = {
                "id": player.id,
                "name": player.name,
                "public_role": player.public_role.value,
                "health": player.health.value,
                "ap": player.ap,
                "is_present": player.is_present,
                "is_human": player.is_human,
            }
            if self.state.finished:
                item["revealed_faction"] = player.hidden_faction.value
            players.append(item)
        public_event = None
        if event:
            public_event = {
                "id": event.id,
                "title": event.title,
                "description": event.description,
                "visible_effect": event.visible_effect,
                "available_solutions": list(event.available_solutions),
                "resource_cost": dict(event.resource_cost),
                "related_facility": event.related_facility,
            }
        return {
            "day": self.state.day,
            "total_days": self.config.total_days,
            "phase": self.state.phase.value,
            "resources": {
                "food": self.state.resources.food,
                "energy": self.state.resources.energy,
                "medicine": self.state.resources.medicine,
                "parts": self.state.resources.parts,
                "stability": self.state.resources.stability,
            },
            "facilities": {
                facility_id: {
                    "name": facility.name,
                    "durability": facility.durability,
                    "condition": facility.condition,
                }
                for facility_id, facility in self.state.facilities.items()
            },
            "players": players,
            "current_event": public_event,
            "proposals": self.view_proposals(player_id),
            "finished": self.state.finished,
        }

    def get_private_state(self, player_id: str) -> dict[str, Any]:
        player = self._player(player_id)
        action_records = [
            {
                "day": action.metadata.get("resolved_day", self.state.day),
                "type": action.type.value,
                "target": action.target,
                "status": action.status.value,
                "result": action.result,
            }
            for action in self.state.action_history + self.state.pending_actions
            if action.player_id == player_id
        ]
        vote_records = [
            {
                "proposal_id": proposal.id,
                "choice": proposal.votes[player_id].value,
                "status": proposal.status.value,
            }
            for proposal in self.state.proposals.values()
            if player_id in proposal.votes
        ]
        trade_records = [
            {
                "id": trade.id,
                "sender_id": trade.sender_id,
                "receiver_id": trade.receiver_id,
                "offer": dict(trade.offer),
                "request": dict(trade.request),
                "promise": trade.promise,
                "status": trade.status.value,
            }
            for trade in self.state.trades.values()
            if player_id in {trade.sender_id, trade.receiver_id}
        ]
        return {
            "player_id": player.id,
            "hidden_faction": player.hidden_faction.value,
            "private_goal": {
                "id": player.private_goal.id,
                "description": player.private_goal.description,
                "completed": player.private_goal.completed,
            }
            if player.private_goal
            else None,
            "personal_resources": dict(player.personal_resources),
            "inventory": dict(player.inventory),
            "personality": dict(player.personality),
            "current_plan": player.current_plan,
            "clues": list(player.clues),
            "turn_memory": list(player.turn_memory),
            "key_memory": list(player.key_memory),
            "cooldowns": dict(player.cooldowns),
            "promises": list(player.promises),
            "action_records": action_records,
            "vote_records": vote_records,
            "trade_records": trade_records,
        }

    def get_current_event(self, player_id: str) -> dict[str, Any] | None:
        return self.get_public_state(player_id)["current_event"]

    def get_relationships(self, player_id: str) -> dict[str, dict[str, Any]]:
        player = self._player(player_id)
        return {
            other_id: {
                "trust": relation.trust,
                "suspicion": relation.suspicion,
                "cooperation": relation.cooperation,
                "honesty": relation.honesty,
                "usefulness": relation.usefulness,
                "known_promises": list(relation.known_promises),
                "broken_promises": list(relation.broken_promises),
            }
            for other_id, relation in player.relationships.items()
        }

    def get_recent_messages(self, player_id: str, limit: int = 20) -> list[dict[str, Any]]:
        self._player(player_id)
        visible = [
            message
            for message in self.state.messages
            if not message.is_private
            or message.sender_id == player_id
            or message.receiver_id == player_id
        ]
        return [
            {
                "day": message.day,
                "phase": message.phase.value,
                "sender_id": message.sender_id,
                "receiver_id": message.receiver_id,
                "content": message.content,
            }
            for message in visible[-max(0, limit) :]
        ]

    def get_public_logs(self, player_id: str, limit: int = 50) -> list[dict[str, Any]]:
        self._player(player_id)
        logs = [entry for entry in self.state.logs if entry.visibility == Visibility.PUBLIC]
        return [self._log_view(entry) for entry in logs[-max(0, limit) :]]

    def get_visible_logs(self, player_id: str, limit: int = 50) -> list[dict[str, Any]]:
        self._player(player_id)
        logs = [
            entry
            for entry in self.state.logs
            if entry.visibility == Visibility.PUBLIC
            or (entry.visibility == Visibility.PRIVATE and player_id in entry.player_ids)
        ]
        return [self._log_view(entry) for entry in logs[-max(0, limit) :]]

    @staticmethod
    def _log_view(entry: LogEntry) -> dict[str, Any]:
        return {
            "id": entry.id,
            "day": entry.day,
            "phase": entry.phase.value,
            "category": entry.category,
            "message": entry.message,
            "data": dict(entry.data),
        }

    def get_available_actions(self, player_id: str) -> list[dict[str, Any]]:
        player = self._player(player_id)
        return [
            {"type": name, "ap_cost": action_ap_cost(player, ActionType(name))}
            for name in available_action_types(self.state, player)
        ]

    # ------------------------------------------------------------------
    # Communication, proposals and trades
    # ------------------------------------------------------------------
    def send_public_message(self, player_id: str, content: str) -> Message:
        self._require_phase(GamePhase.DISCUSSION, GamePhase.EXPULSION)
        player = self._player(player_id)
        if not player.can_speak:
            raise GameRuleError("当前状态不能发言", "SPEECH_RESTRICTED")
        if player.public_messages_today >= 2:
            raise GameRuleError("每天最多公开发言 2 次", "MESSAGE_LIMIT")
        content = content.strip()
        if not content or len(content) > 500:
            raise GameRuleError("发言长度必须为 1 到 500 个字符", "INVALID_MESSAGE")
        message = Message(
            self._next_id("message"), self.state.day, self.state.phase, player_id, content
        )
        self.state.messages.append(message)
        player.public_messages_today += 1
        self._log("public_message", f"{player.name}：{content}")
        return message

    def send_private_message(self, sender_id: str, receiver_id: str, content: str) -> Message:
        self._require_phase(GamePhase.DISCUSSION)
        sender = self._player(sender_id)
        receiver = self._player(receiver_id)
        if sender_id == receiver_id:
            raise GameRuleError("不能给自己发送私聊", "INVALID_RECEIVER")
        if not sender.can_speak or not receiver.is_present:
            raise GameRuleError("发送方或接收方当前不可交流", "SPEECH_RESTRICTED")
        if sender.private_chats_today >= 1:
            raise GameRuleError("每天最多发起 1 次私聊", "PRIVATE_MESSAGE_LIMIT")
        content = content.strip()
        if not content or len(content) > 500:
            raise GameRuleError("私聊长度必须为 1 到 500 个字符", "INVALID_MESSAGE")
        message = Message(
            self._next_id("message"),
            self.state.day,
            self.state.phase,
            sender_id,
            content,
            receiver_id,
        )
        self.state.messages.append(message)
        sender.private_chats_today += 1
        self._log(
            "private_message",
            f"{sender.name} 向 {receiver.name} 发送私聊：{content}",
            Visibility.PRIVATE,
            [sender_id, receiver_id],
        )
        return message


    def propose_plan(self, player_id: str, proposal: Proposal | dict[str, Any]) -> Proposal:
        self._require_phase(GamePhase.DISCUSSION)
        player = self._player(player_id)
        if not player.can_speak:
            raise GameRuleError("当前状态不能提出方案", "PROPOSAL_RESTRICTED")
        if player.proposals_today >= 1:
            raise GameRuleError("每天最多提出 1 个公共方案", "PROPOSAL_LIMIT")
        if not self.state.current_event:
            raise GameRuleError("当前没有可处理事件", "NO_EVENT")

        data = proposal if isinstance(proposal, dict) else {
            "title": proposal.title,
            "description": proposal.description,
            "resource_cost": proposal.resource_cost,
            "participants": proposal.participants,
            "target_event": proposal.target_event,
        }
        title = str(data.get("title", "")).strip()
        description = str(data.get("description", "")).strip()
        target_event = data.get("target_event")
        participants = list(data.get("participants") or [player_id])
        if not title or not description:
            raise GameRuleError("方案标题和描述不能为空", "INVALID_PROPOSAL")
        if target_event != self.state.current_event.id:
            raise GameRuleError("方案必须与当前事件相关", "UNRELATED_PROPOSAL")
        if any(item not in self.state.players or not self.state.players[item].is_present for item in participants):
            raise GameRuleError("方案参与者必须是有效在场玩家", "INVALID_PARTICIPANT")
        if any(
            item.created_day == self.state.day and item.title == title
            for item in self.state.proposals.values()
        ):
            raise GameRuleError("当天不能重复提交相同方案", "DUPLICATE_PROPOSAL")

        rule_cost = dict(self.state.current_event.resource_cost)
        supplied_cost = dict(data.get("resource_cost") or rule_cost)
        if supplied_cost != rule_cost:
            raise GameRuleError("方案资源成本必须采用当前事件规则值", "INVALID_PROPOSAL_COST")
        if not self.state.resources.can_afford(rule_cost):
            raise GameRuleError("当前公共资源不足以提交该方案", "INSUFFICIENT_RESOURCE")
        item = Proposal(
            id=self._next_id("proposal"),
            proposer_id=player_id,
            title=title,
            description=description,
            resource_cost=rule_cost,
            participants=participants,
            expected_effect=dict(self.state.current_event.success_effect),
            target_event=target_event,
            created_day=self.state.day,
        )
        self.state.proposals[item.id] = item
        player.proposals_today += 1
        self._log("proposal", f"{player.name} 提出方案《{title}》", data={"proposal_id": item.id})
        return item

    def view_proposals(self, player_id: str) -> list[dict[str, Any]]:
        self._player(player_id)
        return [
            {
                "id": proposal.id,
                "proposer_id": proposal.proposer_id,
                "title": proposal.title,
                "description": proposal.description,
                "resource_cost": dict(proposal.resource_cost),
                "participants": list(proposal.participants),
                "expected_effect": deepcopy(proposal.expected_effect),
                "target_event": proposal.target_event,
                "votes": {voter: choice.value for voter, choice in proposal.votes.items()},
                "status": proposal.status.value,
            }
            for proposal in self.state.proposals.values()
            if proposal.created_day == self.state.day
        ]

    def vote(self, player_id: str, proposal_id: str, choice: VoteChoice | str) -> None:
        self._require_phase(GamePhase.VOTING)
        player = self._player(player_id)
        if not player.can_vote:
            raise GameRuleError("当前状态不能投票", "VOTE_RESTRICTED")
        try:
            proposal = self.state.proposals[proposal_id]
        except KeyError as exc:
            raise GameRuleError("未知方案", "UNKNOWN_PROPOSAL") from exc
        if proposal.created_day != self.state.day or proposal.status != ProposalStatus.PENDING:
            raise GameRuleError("方案当前不可投票", "PROPOSAL_NOT_PENDING")
        if player_id in proposal.votes:
            raise GameRuleError("不能重复投票", "DUPLICATE_VOTE")
        proposal.votes[player_id] = VoteChoice(choice)
        self._log("vote", f"{player.name} 已对《{proposal.title}》投票")

    @staticmethod
    def _valid_bundle(bundle: dict[str, int]) -> bool:
        return bool(bundle) and all(
            name in {"food", "energy", "medicine", "parts"}
            and isinstance(amount, int)
            and amount > 0
            for name, amount in bundle.items()
        )

    @staticmethod
    def _can_pay(player: Player, bundle: dict[str, int]) -> bool:
        return all(player.personal_resources.get(name, 0) >= amount for name, amount in bundle.items())

    def propose_trade(
        self,
        sender_id: str,
        receiver_id: str,
        offer: dict[str, int],
        request: dict[str, int] | None = None,
        *,
        is_public: bool = False,
        promise: str | None = None,
    ) -> Trade:
        self._require_phase(GamePhase.DISCUSSION)
        sender = self._player(sender_id)
        receiver = self._player(receiver_id)
        if sender_id == receiver_id or not sender.is_present or not receiver.is_present:
            raise GameRuleError("交易双方必须是不同的在场玩家", "INVALID_TRADE_PARTY")
        limit = 2 if sender.public_role == Role.TRADER else 1
        if sender.trades_today >= limit:
            raise GameRuleError(f"本日最多发起 {limit} 次交易", "TRADE_LIMIT")
        request = request or {}
        if not self._valid_bundle(offer) or (request and not self._valid_bundle(request)):
            raise GameRuleError("交易资源名称或数量无效", "INVALID_TRADE_BUNDLE")
        if not self._can_pay(sender, offer):
            raise GameRuleError("发起方个人资源不足", "INSUFFICIENT_RESOURCE")
        if request and not self._can_pay(receiver, request):
            raise GameRuleError("接收方当前没有足够资源", "INSUFFICIENT_RESOURCE")
        trade = Trade(
            self._next_id("trade"),
            sender_id,
            receiver_id,
            dict(offer),
            dict(request),
            is_public,
            promise,
        )
        self.state.trades[trade.id] = trade
        sender.trades_today += 1
        visibility = Visibility.PUBLIC if is_public else Visibility.PRIVATE
        parties = [] if is_public else [sender_id, receiver_id]
        self._log("trade", f"{sender.name} 向 {receiver.name} 发起交易", visibility, parties)
        if promise:
            sender.promises.append(promise)
            receiver.relationships[sender_id].known_promises.append(promise)
        return trade

    def accept_trade(self, player_id: str, trade_id: str) -> Trade:
        self._require_phase(GamePhase.DISCUSSION)
        trade = self._trade_for_receiver(player_id, trade_id)
        sender = self._player(trade.sender_id)
        receiver = self._player(trade.receiver_id)
        if not self._can_pay(sender, trade.offer) or not self._can_pay(receiver, trade.request):
            raise GameRuleError("接受时交易一方资源不足", "INSUFFICIENT_RESOURCE")
        self._move_bundle(sender, receiver, trade.offer)
        self._move_bundle(receiver, sender, trade.request)
        trade.status = TradeStatus.ACCEPTED
        sender.metrics["trades_completed"] = sender.metrics.get("trades_completed", 0) + 1
        receiver.metrics["trades_completed"] = receiver.metrics.get("trades_completed", 0) + 1
        self._log(
            "trade",
            f"{sender.name} 与 {receiver.name} 完成交易",
            Visibility.PUBLIC if trade.is_public else Visibility.PRIVATE,
            [] if trade.is_public else [sender.id, receiver.id],
        )
        return trade

    def reject_trade(self, player_id: str, trade_id: str) -> Trade:
        self._require_phase(GamePhase.DISCUSSION)
        trade = self._trade_for_receiver(player_id, trade_id)
        trade.status = TradeStatus.REJECTED
        self._log(
            "trade",
            f"{self._player(player_id).name} 拒绝了一项交易",
            Visibility.PRIVATE,
            [trade.sender_id, trade.receiver_id],
        )
        return trade

    def counter_trade(
        self,
        player_id: str,
        trade_id: str,
        offer: dict[str, int],
        request: dict[str, int],
    ) -> Trade:
        self._require_phase(GamePhase.DISCUSSION)
        original = self._trade_for_receiver(player_id, trade_id)
        original.status = TradeStatus.COUNTERED
        counter = self.propose_trade(player_id, original.sender_id, offer, request)
        counter.parent_trade_id = original.id
        return counter

    def _trade_for_receiver(self, player_id: str, trade_id: str) -> Trade:
        try:
            trade = self.state.trades[trade_id]
        except KeyError as exc:
            raise GameRuleError("未知交易", "UNKNOWN_TRADE") from exc
        if trade.receiver_id != player_id:
            raise GameRuleError("只有接收方可以处理该交易", "TRADE_PERMISSION")
        if trade.status != TradeStatus.PENDING:
            raise GameRuleError("交易已经处理", "TRADE_NOT_PENDING")
        return trade

    @staticmethod
    def _move_bundle(sender: Player, receiver: Player, bundle: dict[str, int]) -> None:
        for name, amount in bundle.items():
            sender.personal_resources[name] -= amount
            receiver.personal_resources[name] = receiver.personal_resources.get(name, 0) + amount

    # ------------------------------------------------------------------
    # Actions and profession skills
    # ------------------------------------------------------------------
    def perform_action(self, player_id: str, action: Action | dict[str, Any]) -> Action:
        item = self._build_action(player_id, action, is_secret=False)
        if item.type in SECRET_ACTIONS:
            raise GameRuleError("秘密行动必须通过 perform_secret_action 提交", "SECRET_API_REQUIRED")
        return self._queue_action(item)

    def perform_secret_action(self, player_id: str, action: Action | dict[str, Any]) -> Action:
        item = self._build_action(player_id, action, is_secret=True)
        if item.type not in SECRET_ACTIONS:
            raise GameRuleError("该行动不是秘密行动", "NOT_SECRET_ACTION")
        return self._queue_action(item)

    def _build_action(
        self, player_id: str, action: Action | dict[str, Any], *, is_secret: bool
    ) -> Action:
        self._player(player_id)
        if isinstance(action, Action):
            if action.player_id != player_id:
                raise GameRuleError("不能替其他玩家提交行动", "ACTION_PERMISSION")
            action.is_secret = is_secret
            return action
        try:
            action_type = ActionType(action["type"])
        except (KeyError, ValueError) as exc:
            raise GameRuleError("未知或缺失的行动类型", "INVALID_ACTION_TYPE") from exc
        return Action(
            id=self._next_id("action"),
            player_id=player_id,
            type=action_type,
            target=action.get("target"),
            resource=action.get("resource"),
            amount=int(action.get("amount", 0)),
            metadata=dict(action.get("metadata") or {}),
            is_secret=is_secret,
        )

    def _queue_action(self, action: Action) -> Action:
        player = self._player(action.player_id)
        cost = validate_action(self.state, player, action)
        action.ap_cost = cost
        player.ap -= cost
        if action.is_secret:
            player.secret_actions_today += 1
        self.state.pending_actions.append(action)
        self._log(
            "action_queued",
            f"{player.name} 提交了行动 {action.type.value}",
            Visibility.ADMIN if action.is_secret else Visibility.PUBLIC,
            data={"action_id": action.id, "player_id": player.id, "type": action.type.value},
        )
        return action

    def end_turn(self, player_id: str) -> None:
        self._require_phase(GamePhase.ACTION)
        player = self._player(player_id)
        if not player.is_present:
            raise GameRuleError("离场玩家不能结束行动回合", "PLAYER_ABSENT")
        player.ended_turn = True

    def use_skill(self, player_id: str, skill: str, target: str | None = None) -> dict[str, Any]:
        self._require_phase(GamePhase.ACTION)
        player = self._player(player_id)
        if not player.can_act or player.ended_turn:
            raise GameRuleError("当前状态不能使用技能", "SKILL_RESTRICTED")
        role_skills = {
            Role.ENGINEER: ("emergency_repair", 3),
            Role.DOCTOR: ("full_diagnosis", 3),
            Role.GUARD: ("secret_monitoring", 2),
            Role.TRADER: ("resource_exchange", 2),
            Role.RESEARCHER: ("risk_forecast", 3),
        }
        expected, cooldown = role_skills[player.public_role]
        if skill != expected:
            raise GameRuleError("该职业不能使用此技能", "INVALID_SKILL")
        if player.cooldowns.get(skill, 0) > 0:
            raise GameRuleError("技能仍在冷却中", "SKILL_COOLDOWN")
        if player.ap < 1:
            raise GameRuleError("使用技能至少需要 1 AP", "INSUFFICIENT_AP")

        result: dict[str, Any] = {"skill": skill, "target": target}
        if player.public_role == Role.ENGINEER:
            if target not in self.state.facilities:
                raise GameRuleError("紧急抢修需要指定设施", "INVALID_FACILITY")
            if self.state.resources.parts < 1:
                raise GameRuleError("紧急抢修需要 1 个零件", "INSUFFICIENT_RESOURCE")
            self.state.resources.change("parts", -1)
            result["durability_change"] = self.state.facilities[target].change(30)
            player.metrics["repair_count"] += 1
            self._log("skill", f"{player.name} 对 {target} 进行了紧急抢修")
        elif player.public_role == Role.DOCTOR:
            patient = self._player(target or "")
            if not patient.is_present:
                raise GameRuleError("不能治疗离场玩家", "INVALID_PLAYER")
            if self.state.resources.medicine < 2:
                raise GameRuleError("全面诊疗需要 2 份药品", "INSUFFICIENT_RESOURCE")
            self.state.resources.change("medicine", -2)
            old = patient.health
            patient.health = improve_health(patient.health, 2)
            result["health_change"] = f"{old.value}->{patient.health.value}"
            player.metrics["heal_count"] += 1
            self._log("skill", f"{player.name} 对 {patient.name} 进行了全面诊疗")
        elif player.public_role == Role.GUARD:
            target_player = self._player(target or "")
            actions = [
                item.type.value
                for item in self.state.action_history
                if item.player_id == target_player.id and item.metadata.get("resolved_day") == self.state.day - 1
            ]
            result["observed_action_types"] = actions or ["未发现行动记录"]
            self._log(
                "skill",
                f"秘密监控结果：{target_player.name} 上一天行动类型为 {result['observed_action_types']}",
                Visibility.PRIVATE,
                [player.id],
            )
        elif player.public_role == Role.TRADER:
            if target not in {"food", "energy", "medicine", "parts"}:
                raise GameRuleError("资源置换需要指定目标资源", "INVALID_RESOURCE")
            sources = [
                name
                for name, amount in player.personal_resources.items()
                if name != target and amount > 0
            ]
            if not sources:
                raise GameRuleError("没有可用于置换的个人资源", "INSUFFICIENT_RESOURCE")
            source = max(sources, key=lambda name: player.personal_resources[name])
            player.personal_resources[source] -= 1
            player.personal_resources[target] = player.personal_resources.get(target, 0) + 2
            result["exchange"] = {"spent": {source: 1}, "received": {target: 2}}
            self._log("skill", f"{player.name} 使用了资源置换")
        else:
            if self._event_index < len(self._event_deck):
                next_event = self._event_deck[self._event_index]
                hint = {
                    "difficulty": "高" if next_event.difficulty >= 3 else "低",
                    "related_facility": next_event.related_facility,
                }
            else:
                hint = {"difficulty": "未知", "related_facility": None}
            result["forecast"] = hint
            player.metrics["events_analyzed"] += 1
            self._log(
                "skill",
                f"风险预测提示：{hint}",
                Visibility.PRIVATE,
                [player.id],
            )

        player.ap -= 1
        player.cooldowns[skill] = cooldown
        return result

    # ------------------------------------------------------------------
    # Expulsion
    # ------------------------------------------------------------------
    def nominate_for_expulsion(self, nominator_id: str, target_id: str) -> ExpulsionCase:
        self._require_phase(GamePhase.EXPULSION)
        if self.state.day % 2 != 0:
            raise GameRuleError("每两天最多发起一次驱逐", "EXPULSION_INTERVAL")
        nominator = self._player(nominator_id)
        target = self._player(target_id)
        if not nominator.can_vote or not target.is_present or nominator_id == target_id:
            raise GameRuleError("提名者或目标无效", "INVALID_NOMINATION")
        case = self.state.expulsion or ExpulsionCase(day=self.state.day)
        if case.resolved:
            raise GameRuleError("本次驱逐已经结束", "EXPULSION_RESOLVED")
        if any(nominator_id in nominators for nominators in case.nominations.values()):
            raise GameRuleError("每名玩家本轮只能提名一次", "DUPLICATE_NOMINATION")
        case.nominations.setdefault(target_id, set()).add(nominator_id)
        case.target_id = case.target_id or nominated_target(case)
        self.state.expulsion = case
        self._log("expulsion_nomination", f"{nominator.name} 提名驱逐 {target.name}")
        if case.target_id:
            self._log("expulsion_nomination", f"{target.name} 已获得联合提名，可以公开辩护")
        return case

    def submit_defense(self, player_id: str, content: str) -> None:
        self._require_phase(GamePhase.EXPULSION)
        case = self.state.expulsion
        if not case or case.target_id != player_id:
            raise GameRuleError("只有被联合提名者可以辩护", "DEFENSE_PERMISSION")
        if case.defense is not None:
            raise GameRuleError("辩护机会已经使用", "DUPLICATE_DEFENSE")
        content = content.strip()
        if not content:
            raise GameRuleError("辩护内容不能为空", "INVALID_MESSAGE")
        case.defense = content
        self._log("expulsion_defense", f"{self._player(player_id).name} 辩护：{content}")

    def vote_expulsion(self, player_id: str, support: bool) -> None:
        self._require_phase(GamePhase.EXPULSION)
        player = self._player(player_id)
        case = self.state.expulsion
        if not player.can_vote:
            raise GameRuleError("当前状态不能参与驱逐投票", "VOTE_RESTRICTED")
        if not case or not case.target_id:
            raise GameRuleError("尚未形成联合提名", "NO_EXPULSION_TARGET")
        if player_id in case.votes:
            raise GameRuleError("不能重复进行驱逐投票", "DUPLICATE_VOTE")
        case.votes[player_id] = bool(support)
        self._log(
            "expulsion_vote",
            f"{player.name} 已提交秘密驱逐票",
            Visibility.PUBLIC,
        )
        self._log(
            "expulsion_vote_detail",
            f"{player.name} 的驱逐票为 {'赞成' if support else '反对'}",
            Visibility.ADMIN,
        )

    def _resolve_expulsion(self) -> None:
        case = self.state.expulsion
        if not case or not case.target_id:
            self._log("expulsion", "本日未形成有效联合提名，驱逐取消")
            return
        eligible = {player.id for player in voting_players(self.state)}
        case.expelled = expulsion_passed(case, eligible)
        case.resolved = True
        target = self._player(case.target_id)
        if not case.expelled:
            self._log("expulsion", f"对 {target.name} 的驱逐未获严格过半支持")
            return

        target.health = HealthStatus.EXPELLED
        target.expelled_day = self.state.day
        if target.hidden_faction == Faction.SURVIVOR:
            self.state.resources.change("stability", -8)
            self._log("expulsion", f"{target.name} 被驱逐；身份将在游戏结束后公开。稳定度 -8")
        else:
            self._log("expulsion", f"{target.name} 被驱逐；身份将在游戏结束后公开。")
            for voter_id, support in case.votes.items():
                if support:
                    voter = self._player(voter_id)
                    voter.metrics["voted_true_saboteur"] = 1
        self._log(
            "expulsion_identity",
            f"系统记录：{target.name} 的真实阵营是 {target.hidden_faction.value}",
            Visibility.ADMIN,
        )

    # ------------------------------------------------------------------
    # State machine and resolution
    # ------------------------------------------------------------------
    def advance_phase(self) -> GamePhase:
        if self.state.finished:
            return GamePhase.FINISHED
        if self.state.step_count >= self.config.max_steps:
            self._finish_game(False, "达到最大步骤限制")
            return GamePhase.FINISHED
        self.state.step_count += 1

        if self.state.phase == GamePhase.EVENT:
            self.state.phase = GamePhase.DISCUSSION
        elif self.state.phase == GamePhase.DISCUSSION:
            self.state.phase = GamePhase.ACTION
            for player in self.state.players.values():
                player.ap = player.daily_ap()
        elif self.state.phase == GamePhase.ACTION:
            self.state.phase = GamePhase.VOTING
        elif self.state.phase == GamePhase.VOTING:
            self._close_public_votes()
            self.state.phase = GamePhase.RESOLUTION
        elif self.state.phase == GamePhase.RESOLUTION:
            self._resolve_day()
            if not self.state.finished:
                if self.state.day % 2 == 0 and self.state.day < self.config.total_days:
                    self.state.phase = GamePhase.EXPULSION
                    self.state.expulsion = ExpulsionCase(day=self.state.day)
                else:
                    self._next_day()
        elif self.state.phase == GamePhase.EXPULSION:
            self._resolve_expulsion()
            reason = collapse_reason(self.state)
            if reason:
                self._finish_game(False, reason)
            else:
                self._next_day()
        return self.state.phase

    def _close_public_votes(self) -> None:
        eligible = {player.id for player in voting_players(self.state)}
        for proposal in self.state.proposals.values():
            if proposal.created_day != self.state.day or proposal.status != ProposalStatus.PENDING:
                continue
            status = resolve_vote(proposal, eligible)
            support = sum(choice == VoteChoice.SUPPORT for choice in proposal.votes.values())
            self._log(
                "proposal_vote_result",
                f"方案《{proposal.title}》{('通过' if status == ProposalStatus.PASSED else '未通过')}（支持 {support}/{len(eligible)}）",
            )

    def _resolve_day(self) -> None:
        self._resolve_proposals()
        self._protections.clear()
        public_actions = [item for item in self.state.pending_actions if not item.is_secret]
        secret_actions = [item for item in self.state.pending_actions if item.is_secret]
        for action in public_actions + secret_actions:
            self._resolve_action(action)
        self.state.action_history.extend(self.state.pending_actions)
        self.state.pending_actions = []
        self._consume_daily_resources()
        if not self.state.handled_event and self.state.current_event:
            changes = apply_structured_effect(
                self.state, self.state.current_event.failure_effect, self.rng
            )
            self._log(
                "event_failure",
                f"事件《{self.state.current_event.title}》未妥善处理：{', '.join(changes) or '无直接变化'}",
            )
        self._apply_facility_penalties()
        self.state.food_zero_days = self.state.food_zero_days + 1 if self.state.resources.food == 0 else 0
        self.state.energy_zero_days = (
            self.state.energy_zero_days + 1 if self.state.resources.energy == 0 else 0
        )
        self._compress_daily_memory()

        reason = collapse_reason(self.state)
        if reason:
            self._finish_game(False, reason)
        elif self.state.day >= self.config.total_days:
            survived = shelter_survived(self.state)
            self._finish_game(survived, None if survived else "最终生存条件未满足")

    def _resolve_proposals(self) -> None:
        for proposal in self.state.proposals.values():
            if proposal.created_day != self.state.day or proposal.status != ProposalStatus.PASSED:
                continue
            # Costs and effects are always reloaded from the rule-owned event.
            # A caller cannot mutate the returned Proposal object to create resources.
            event = self.state.current_event
            if not event or proposal.target_event != event.id:
                proposal.status = ProposalStatus.FAILED
                self._log("proposal_execution", f"方案《{proposal.title}》与当前事件不匹配")
                continue
            rule_cost = dict(event.resource_cost)
            rule_effect = deepcopy(event.success_effect)
            if not self.state.resources.can_afford(rule_cost):
                proposal.status = ProposalStatus.FAILED
                self._log("proposal_execution", f"方案《{proposal.title}》因资源不足无法执行")
                continue
            self.state.resources.spend(rule_cost)
            changes = apply_structured_effect(self.state, rule_effect, self.rng)
            if self.state.current_event and proposal.target_event == self.state.current_event.id:
                self.state.handled_event = True
                if any(
                    self.state.players[player_id].public_role == self.state.current_event.role_bonus
                    for player_id in proposal.participants
                    if player_id in self.state.players
                ):
                    self.state.resources.change("stability", 2)
                    changes.append("职业协作奖励 stability +2")
            proposal.status = ProposalStatus.IMPLEMENTED
            proposer = self._player(proposal.proposer_id)
            proposer.metrics["proposals_passed"] += 1
            self._log(
                "proposal_execution",
                f"方案《{proposal.title}》已执行：{', '.join(changes) or '事件风险已受控'}",
            )

    def _resolve_action(self, action: Action) -> None:
        player = self._player(action.player_id)
        action.metadata["resolved_day"] = self.state.day
        try:
            result = self._apply_action_effect(player, action)
            action.status = ActionStatus.RESOLVED
            action.result = result
        except GameRuleError as exc:
            action.status = ActionStatus.REJECTED
            action.result = exc.message
        if action.is_secret:
            self._log(
                "secret_action_detail",
                f"{player.name} 执行 {action.type.value}：{action.result}",
                Visibility.ADMIN,
                data={"action_id": action.id, "actor": player.id},
            )
        else:
            self._log("action_result", f"{player.name}：{action.result}")

    def _spend_public(self, resource: str, amount: int, reason: str) -> None:
        if self.state.resources.get(resource) < amount:
            raise GameRuleError(f"{reason}失败：{resource} 不足", "INSUFFICIENT_RESOURCE")
        self.state.resources.change(resource, -amount)

    def _apply_action_effect(self, player: Player, action: Action) -> str:
        kind = action.type
        if kind == ActionType.EXPLORE:
            communication = self.state.facilities["communication_system"].durability
            penalty = 2 if communication < 20 else 1 if communication < 50 else 0
            food = max(1, self.rng.randint(3, 6) - penalty)
            parts = max(0, self.rng.randint(1, 3) - penalty)
            self.state.resources.change("food", food)
            self.state.resources.change("parts", parts)
            personal_food = 1
            personal_parts = 1 if parts > 0 else 0
            player.personal_resources["food"] = (
                player.personal_resources.get("food", 0) + personal_food
            )
            if personal_parts:
                player.personal_resources["parts"] = (
                    player.personal_resources.get("parts", 0) + personal_parts
                )
            return (
                f"探索获得公共 food +{food}、parts +{parts}；"
                f"个人 food +{personal_food}、parts +{personal_parts}"
            )
        if kind == ActionType.REPAIR:
            self._spend_public("parts", 2, "修理")
            amount = 25 if player.public_role == Role.ENGINEER else 15
            actual = self.state.facilities[action.target or ""].change(amount)
            player.metrics["repair_count"] += 1
            return f"修理 {action.target}，durability {actual:+d}"
        if kind == ActionType.INVESTIGATE:
            target = action.target or ""
            if target in self.state.players:
                suspect = self.state.players[target]
                if suspect.hidden_faction == Faction.SABOTEUR:
                    clue = f"{suspect.name} 的部分行动时间与记录不一致，但证据不完整。"
                    player.relationships[suspect.id].apply(suspicion=35, trust=-10)
                else:
                    clue = f"关于 {suspect.name} 未发现决定性证据，仍需交叉验证。"
                    player.relationships[suspect.id].apply(suspicion=-10, trust=5)
            elif target in self.state.facilities:
                facility = self.state.facilities[target]
                clue = f"{facility.name} 当前为{facility.condition}，损伤原因无法唯一确定。"
            else:
                event = self.state.current_event
                clue = f"事件风险可能与 {event.related_facility or '内部关系'} 有关，具体原因未知。"
                player.metrics["events_analyzed"] += 1
            player.clues.append(clue)
            self._log("clue", clue, Visibility.PRIVATE, [player.id])
            return "调查完成，获得一条不完整线索"
        if kind == ActionType.HEAL:
            patient = self._player(action.target or "")
            self._spend_public("medicine", 2, "治疗")
            old = patient.health
            levels = 2 if player.public_role == Role.DOCTOR else 1
            patient.health = improve_health(patient.health, levels)
            player.metrics["heal_count"] += 1
            return f"治疗 {patient.name}：{old.value}->{patient.health.value}"
        if kind == ActionType.CRAFT:
            cost = 1 if player.public_role == Role.RESEARCHER else 2
            self._spend_public("parts", cost, "制造")
            item = action.target or "repair_kit"
            player.inventory[item] = player.inventory.get(item, 0) + 1
            player.metrics["craft_count"] += 1
            return f"制造 {item} 成功"
        if kind == ActionType.SEARCH:
            resource = self.rng.choice(["food", "energy", "medicine", "parts"])
            amount = self.rng.randint(1, 3)
            self.state.resources.change(resource, amount)
            return f"搜索获得 {resource} +{amount}"
        if kind == ActionType.TRANSFER_RESOURCE:
            receiver = self._player(action.target or "")
            resource = action.resource or ""
            if player.personal_resources.get(resource, 0) < action.amount:
                raise GameRuleError("执行转移时个人资源不足", "INSUFFICIENT_RESOURCE")
            player.personal_resources[resource] -= action.amount
            receiver.personal_resources[resource] = receiver.personal_resources.get(resource, 0) + action.amount
            return f"向 {receiver.name} 转移 {resource} {action.amount}"
        if kind == ActionType.MINOR_HEAL:
            patient = self._player(action.target or "")
            self._spend_public("medicine", 1, "简单治疗")
            old = patient.health
            patient.health = improve_health(patient.health, 1)
            player.metrics["heal_count"] += 1
            return f"简单治疗 {patient.name}：{old.value}->{patient.health.value}"
        if kind == ActionType.REINFORCE:
            self._spend_public("parts", 1, "加固")
            actual = self.state.facilities[action.target or ""].change(8)
            return f"加固 {action.target}，durability {actual:+d}"
        if kind == ActionType.PROTECT:
            self._protections[action.target or ""] = player.id
            return f"保护 {action.target}，可阻止本日一次秘密破坏"
        if kind == ActionType.REST:
            old = player.health
            player.health = improve_health(player.health, 1)
            return f"休息：{old.value}->{player.health.value}"
        if kind == ActionType.PERSUADE:
            target = self._player(action.target or "")
            player.relationships[target.id].apply(trust=3, cooperation=5)
            target.relationships[player.id].apply(trust=2, cooperation=3)
            return f"与 {target.name} 建立合作意向"
        if kind == ActionType.SABOTAGE:
            target = action.target or ""
            if target in self._protections:
                guard = self._player(self._protections[target])
                guard.metrics["prevented_sabotage"] += 1
                self._log("secret_incident", f"夜间，{target} 附近出现异常，但破坏被保护措施阻止。")
                return f"破坏 {target} 被警卫保护阻止"
            damage = self.rng.randint(22, 30)
            actual = self.state.facilities[target].change(-damage)
            player.metrics["sabotage_count"] += 1
            player.metrics["lowest_sabotaged_facility_durability"] = min(
                player.metrics.get("lowest_sabotaged_facility_durability", 100),
                self.state.facilities[target].durability,
            )
            self._log("secret_incident", f"夜间，{target} 出现异常损坏，原因未知。")
            self._leave_incomplete_clue(player, target)
            return f"秘密破坏 {target}，durability {actual:+d}"
        if kind == ActionType.STEAL:
            resource = action.resource or ""
            amount = min(self.rng.randint(3, 5), self.state.resources.get(resource))
            self.state.resources.change(resource, -amount)
            player.personal_resources[resource] = player.personal_resources.get(resource, 0) + amount
            player.metrics["sabotage_count"] += 1
            self._log("secret_incident", f"夜间，部分 {resource} 不翼而飞，执行者未知。")
            self._leave_incomplete_clue(player, resource)
            return f"秘密偷窃 {resource} {amount}"
        if kind == ActionType.SPREAD_RUMOR:
            target = action.target or ""
            if target in self._protections:
                guard = self._player(self._protections[target])
                guard.metrics["prevented_sabotage"] += 1
                return "谣言被保护者及时澄清"
            self.state.resources.change("stability", -2)
            player.metrics["sabotage_count"] += 1
            self._log("secret_incident", "避难所内出现来源不明的传言，稳定度 -2。")
            self._leave_incomplete_clue(player, target)
            return f"针对 {target} 制造谣言"
        raise GameRuleError("未实现的行动类型", "INVALID_ACTION_TYPE")

    def _leave_incomplete_clue(self, actor: Player, target: str) -> None:
        observers = [player for player in active_players(self.state) if player.id != actor.id]
        if not observers:
            return
        observer = self.rng.choice(observers)
        decoys = [player for player in active_players(self.state) if player.id not in {actor.id, observer.id}]
        repeated = actor.metrics.get("sabotage_count", 0) >= 2
        if repeated:
            clue = f"交叉线索：{actor.name} 多次出现在与 {target} 有关的异常时段。"
            observer.relationships[actor.id].apply(suspicion=35, trust=-10)
        else:
            names = [actor.name]
            if decoys:
                decoy = self.rng.choice(decoys)
                names.append(decoy.name)
                observer.relationships[decoy.id].apply(suspicion=8)
            self.rng.shuffle(names)
            clue = f"弱线索：有人看见 {' 或 '.join(names)} 曾接近与 {target} 有关的区域。"
            observer.relationships[actor.id].apply(suspicion=20, trust=-5)
        observer.clues.append(clue)
        self._log("clue", clue, Visibility.PRIVATE, [observer.id])

    def _consume_daily_resources(self) -> None:
        count = len(active_players(self.state))
        food_cost = count
        power = self.state.facilities["power_system"].durability
        energy_cost = max(2, math.ceil(count / 2)) + (4 if power < 20 else 2 if power < 50 else 0)
        food_change = self.state.resources.change("food", -food_cost)
        energy_change = self.state.resources.change("energy", -energy_cost)
        self._log(
            "daily_consumption",
            f"每日消耗：food {food_change:+d}，energy {energy_change:+d}",
        )

    def _apply_facility_penalties(self) -> None:
        water = self.state.facilities["water_system"].durability
        medical = self.state.facilities["medical_system"].durability
        communication = self.state.facilities["communication_system"].durability
        changes: list[str] = []
        if water < 50:
            changes.append(f"food {self.state.resources.change('food', -1):+d}")
        if water < 20:
            changes.append(f"medicine {self.state.resources.change('medicine', -1):+d}")
            changes.append(f"stability {self.state.resources.change('stability', -2):+d}")
        if medical < 20 and active_players(self.state):
            patient = self.rng.choice(active_players(self.state))
            if patient.health == HealthStatus.SERIOUSLY_INJURED:
                patient.health = HealthStatus.UNCONSCIOUS
                changes.append(f"{patient.name} 因医疗系统失效而昏迷")
        if communication < 20:
            changes.append(f"stability {self.state.resources.change('stability', -1):+d}")
        if changes:
            self._log("facility_penalty", "设施状态造成额外后果：" + "，".join(changes))

    def _compress_daily_memory(self) -> None:
        public_entries = [
            entry.message
            for entry in self.state.logs
            if entry.day == self.state.day and entry.visibility == Visibility.PUBLIC
        ]
        summary = "；".join(public_entries[-5:])[:600]
        for player in self.state.players.values():
            if summary:
                player.key_memory.append(f"第{self.state.day}天：{summary}")
                player.key_memory[:] = player.key_memory[-12:]
            player.turn_memory.clear()

    def _next_day(self) -> None:
        self.state.day += 1
        if self.state.day > self.config.total_days:
            self._finish_game(shelter_survived(self.state), None)
            return
        for player in self.state.players.values():
            player.reset_for_day()
        self.state.expulsion = None
        self.state.phase = GamePhase.EVENT
        self._draw_event()

    def _finish_game(self, survived: bool, reason: str | None) -> None:
        if self.state.finished:
            return
        self.state.finished = True
        self.state.phase = GamePhase.FINISHED
        saboteurs = [
            player for player in self.state.players.values() if player.hidden_faction == Faction.SABOTEUR
        ]
        hidden_objective_met = any(
            evaluate_private_goal(self.state, player) for player in saboteurs
        )
        saboteur_condition = bool(saboteurs) and (
            (not survived) or self.state.resources.stability < 25 or hidden_objective_met
        )
        early_expelled = any(
            player.expelled_day is not None and player.expelled_day < 4 for player in saboteurs
        )
        if saboteur_condition and early_expelled:
            faction_winner = "SABOTEUR_PARTIAL"
        elif saboteur_condition:
            faction_winner = "SABOTEUR"
        else:
            faction_winner = "SURVIVORS"

        player_results: dict[str, dict[str, Any]] = {}
        scores: dict[str, int] = {}
        for player in self.state.players.values():
            goal = evaluate_private_goal(self.state, player)
            if player.hidden_faction == Faction.SABOTEUR:
                complete = saboteur_condition and not early_expelled
                outcome = "完全胜利" if complete else "部分胜利" if saboteur_condition else "失败"
            else:
                survivor_faction_won = faction_winner == "SURVIVORS"
                complete = survivor_faction_won and survived and goal
                outcome = (
                    "完全胜利"
                    if complete
                    else "避难所存活，但未阻止破坏者"
                    if survived and not survivor_faction_won
                    else "生存成功，但个人目标未完成"
                    if survived and survivor_faction_won
                    else "失败"
                )
            score = player_score(self.state, player, survived, goal)
            scores[player.id] = score
            player_results[player.id] = {
                "name": player.name,
                "faction": player.hidden_faction.value,
                "outcome": outcome,
                "private_goal_completed": goal,
                "score": score,
                "strategy_summary": self._strategy_summary(player),
            }

        influence = max(scores, key=scores.get) if scores else None
        trust_received = {
            player.id: sum(
                other.relationships[player.id].trust
                for other in self.state.players.values()
                if player.id in other.relationships
            )
            for player in self.state.players.values()
        }
        suspicion_received = {
            player.id: sum(
                other.relationships[player.id].suspicion
                for other in self.state.players.values()
                if player.id in other.relationships
            )
            for player in self.state.players.values()
        }
        summary = {
            "most_influential": influence,
            "most_trusted": max(trust_received, key=trust_received.get) if trust_received else None,
            "most_suspicious": max(suspicion_received, key=suspicion_received.get)
            if suspicion_received
            else None,
            "expulsion_correct": any(
                player.hidden_faction == Faction.SABOTEUR
                and player.health == HealthStatus.EXPELLED
                for player in self.state.players.values()
            ),
        }
        summary.update(build_postgame_review(self.state, scores))
        self.state.result = GameResult(
            shelter_survived=survived,
            collapse_reason=reason,
            faction_winner=faction_winner,
            player_results=player_results,
            scores=scores,
            revealed_identities={
                player.id: player.hidden_faction.value for player in self.state.players.values()
            },
            summary=summary,
        )
        self._log(
            "game_result",
            f"游戏结束：阵营结果 {faction_winner}，避难所{'存活' if survived else '崩溃'}。",
        )

    @staticmethod
    def _strategy_summary(player: Player) -> str:
        if player.hidden_faction == Faction.SABOTEUR:
            return f"执行 {player.metrics.get('sabotage_count', 0)} 次秘密干扰，并维持公开伪装。"
        return (
            f"完成修理 {player.metrics.get('repair_count', 0)} 次、治疗 "
            f"{player.metrics.get('heal_count', 0)} 次、交易 {player.metrics.get('trades_completed', 0)} 次。"
        )

    def get_admin_state(self) -> dict[str, Any]:
        """Return a clearly marked debug-only system view; never pass it to an agent."""
        return {
            "debug_view": True,
            "day": self.state.day,
            "phase": self.state.phase.value,
            "identities": {
                player.id: player.hidden_faction.value for player in self.state.players.values()
            },
            "secret_actions": [
                {
                    "player_id": action.player_id,
                    "type": action.type.value,
                    "target": action.target,
                    "result": action.result,
                }
                for action in self.state.action_history
                if action.is_secret
            ],
            "hidden_event_risk": self.state.current_event.hidden_risk
            if self.state.current_event
            else None,
            "admin_logs": [
                self._log_view(entry)
                for entry in self.state.logs
                if entry.visibility == Visibility.ADMIN
            ],
        }
