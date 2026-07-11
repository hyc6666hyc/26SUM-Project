from __future__ import annotations

import json

from agents.fallback import RuleBasedBot
from agents.memory import update_agent_memory
from agents.schemas import AgentDecision
from game.engine import GameEngine
from game.enums import Faction, Role, Visibility
from game.views import PlayerView
from services.llm_client import LLMClient


class LLMAgent:
    """Permission-filtered structured LLM controller with deterministic fallback."""

    def __init__(self, client: LLMClient, fallback: RuleBasedBot | None = None) -> None:
        self.client = client
        self.fallback = fallback or RuleBasedBot()

    def decide(self, engine: GameEngine, player_id: str) -> AgentDecision:
        player = engine.state.players[player_id]
        view = PlayerView(engine, player_id)
        model = (
            engine.config.strategy_agent_model
            if player.hidden_faction == Faction.SABOTEUR or player.public_role == Role.GUARD
            else engine.config.normal_agent_model
        )
        allowed_context = {
            "public_state": view.public_state(),
            "private_state": view.private_state(),
            "relationships": view.relationships(),
            "recent_messages": view.recent_messages(12),
            "available_actions": view.available_actions(),
        }
        schema = AgentDecision.model_json_schema()
        messages = [
            {
                "role": "system",
                "content": (
                    "你是避难所议会玩家。只依据提供的权限视图做一次有限决策。"
                    "只输出符合 schema 的 JSON；不要输出隐藏思维链，只给简短策略摘要。"
                    "数值、合法性和随机结果全部交给 Python 规则引擎。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"context": allowed_context, "output_schema": schema},
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ]
        decision = self.client.generate_structured(messages, AgentDecision, model)
        if decision is None:
            engine._log(
                "llm_error",
                f"{player.name} 的模型决策失败，已切换规则 Bot：{self.client.last_error}",
                Visibility.ADMIN,
                [player_id],
            )
            return self.fallback.decide(engine, player_id)
        update_agent_memory(player, decision.memory_update)
        player.current_plan = decision.strategy_summary.strip()[:300]
        for other_id, delta in decision.relationship_updates.items():
            if other_id in player.relationships:
                player.relationships[other_id].apply(
                    trust=delta.trust_delta,
                    suspicion=delta.suspicion_delta,
                    cooperation=delta.cooperation_delta,
                )
        return decision
