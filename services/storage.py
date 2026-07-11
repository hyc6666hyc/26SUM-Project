from __future__ import annotations

import ast
import json
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from game.engine import GameEngine
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
from game.models import (
    Action,
    ExpulsionCase,
    Facility,
    GameConfig,
    GameResult,
    GoalCondition,
    LogEntry,
    Message,
    Player,
    PrivateGoal,
    Proposal,
    Relationship,
    Resources,
    Trade,
)


def to_primitive(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {item.name: to_primitive(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_primitive(item) for item in value]
    return value


class JSONStorage:
    """Versioned JSON save/load for complete deterministic match state."""

    FORMAT_VERSION = 1

    @classmethod
    def save(cls, engine: GameEngine, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format_version": cls.FORMAT_VERSION,
            "config": to_primitive(engine.config),
            "state": to_primitive(engine.state),
            "event_order": list(engine.event_order),
            "event_index": engine._event_index,
            "counters": dict(engine._counters),
            "random_state": repr(engine.rng.getstate()),
        }
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
        return target

    @classmethod
    def load(cls, path: str | Path) -> GameEngine:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("format_version") != cls.FORMAT_VERSION:
            raise ValueError("不支持的存档版本")
        engine = GameEngine(GameConfig(**payload["config"]))
        raw = payload["state"]
        state = engine.state
        state.day = int(raw["day"])
        state.phase = GamePhase(raw["phase"])
        state.resources = Resources(**raw["resources"])
        state.facilities = {
            key: Facility(**item) for key, item in raw["facilities"].items()
        }
        state.players = {
            key: cls._player(item) for key, item in raw["players"].items()
        }
        events_by_id = {event.id: event for event in engine._event_deck}
        current = raw.get("current_event")
        state.current_event = events_by_id.get(current["id"]) if current else None
        state.proposals = {
            key: cls._proposal(item) for key, item in raw["proposals"].items()
        }
        state.trades = {key: cls._trade(item) for key, item in raw["trades"].items()}
        state.pending_actions = [cls._action(item) for item in raw["pending_actions"]]
        state.action_history = [cls._action(item) for item in raw["action_history"]]
        state.messages = [
            Message(
                id=item["id"],
                day=item["day"],
                phase=GamePhase(item["phase"]),
                sender_id=item["sender_id"],
                content=item["content"],
                receiver_id=item.get("receiver_id"),
            )
            for item in raw["messages"]
        ]
        state.logs = [
            LogEntry(
                id=item["id"],
                day=item["day"],
                phase=GamePhase(item["phase"]),
                category=item["category"],
                message=item["message"],
                visibility=Visibility(item["visibility"]),
                player_ids=item["player_ids"],
                data=item["data"],
            )
            for item in raw["logs"]
        ]
        case = raw.get("expulsion")
        state.expulsion = (
            ExpulsionCase(
                day=case["day"],
                nominations={key: set(value) for key, value in case["nominations"].items()},
                target_id=case.get("target_id"),
                defense=case.get("defense"),
                votes={key: bool(value) for key, value in case["votes"].items()},
                resolved=case["resolved"],
                expelled=case["expelled"],
            )
            if case
            else None
        )
        for name in (
            "food_zero_days",
            "energy_zero_days",
            "step_count",
            "finished",
            "handled_event",
        ):
            setattr(state, name, raw[name])
        result = raw.get("result")
        state.result = GameResult(**result) if result else None

        order = payload["event_order"]
        engine._event_deck = [events_by_id[event_id] for event_id in order]
        engine.event_order = order
        engine._event_index = int(payload["event_index"])
        engine._counters = {key: int(value) for key, value in payload["counters"].items()}
        engine.rng.setstate(ast.literal_eval(payload["random_state"]))
        return engine

    @staticmethod
    def _player(item: dict[str, Any]) -> Player:
        goal_data = item.get("private_goal")
        goal = None
        if goal_data:
            goal = PrivateGoal(
                id=goal_data["id"],
                description=goal_data["description"],
                conditions=[GoalCondition(**condition) for condition in goal_data["conditions"]],
                completed=goal_data["completed"],
            )
        return Player(
            id=item["id"],
            name=item["name"],
            public_role=Role(item["public_role"]),
            hidden_faction=Faction(item["hidden_faction"]),
            is_human=item["is_human"],
            health=HealthStatus(item["health"]),
            ap=item["ap"],
            private_goal=goal,
            personal_resources=item["personal_resources"],
            inventory=item["inventory"],
            personality=item["personality"],
            current_plan=item.get("current_plan", ""),
            relationships={key: Relationship(**value) for key, value in item["relationships"].items()},
            turn_memory=item["turn_memory"],
            key_memory=item["key_memory"],
            clues=item["clues"],
            promises=item["promises"],
            metrics=item["metrics"],
            cooldowns=item["cooldowns"],
            public_messages_today=item["public_messages_today"],
            private_chats_today=item["private_chats_today"],
            proposals_today=item["proposals_today"],
            trades_today=item["trades_today"],
            secret_actions_today=item["secret_actions_today"],
            ended_turn=item["ended_turn"],
            expelled_day=item.get("expelled_day"),
        )

    @staticmethod
    def _action(item: dict[str, Any]) -> Action:
        return Action(
            id=item["id"],
            player_id=item["player_id"],
            type=ActionType(item["type"]),
            target=item.get("target"),
            resource=item.get("resource"),
            amount=item["amount"],
            metadata=item["metadata"],
            is_secret=item["is_secret"],
            ap_cost=item["ap_cost"],
            status=ActionStatus(item["status"]),
            result=item["result"],
        )

    @staticmethod
    def _proposal(item: dict[str, Any]) -> Proposal:
        return Proposal(
            id=item["id"],
            proposer_id=item["proposer_id"],
            title=item["title"],
            description=item["description"],
            resource_cost=item["resource_cost"],
            participants=item["participants"],
            expected_effect=item["expected_effect"],
            target_event=item.get("target_event"),
            votes={key: VoteChoice(value) for key, value in item["votes"].items()},
            status=ProposalStatus(item["status"]),
            created_day=item["created_day"],
        )

    @staticmethod
    def _trade(item: dict[str, Any]) -> Trade:
        return Trade(
            id=item["id"],
            sender_id=item["sender_id"],
            receiver_id=item["receiver_id"],
            offer=item["offer"],
            request=item["request"],
            is_public=item["is_public"],
            promise=item.get("promise"),
            status=TradeStatus(item["status"]),
            parent_trade_id=item.get("parent_trade_id"),
        )
