from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agents.llm_agent import LLMAgent
from game.autoplay import AutoGameRunner
from game.config import load_game_config
from game.engine import GameEngine
from services.llm_client import LLMClient
from services.logger import export_replay
from services.storage import JSONStorage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="避难所议会后端自动对局")
    parser.add_argument("--config", default="config/game_config.yaml", help="游戏配置文件")
    parser.add_argument("--seed", type=int, help="覆盖配置中的随机种子")
    parser.add_argument("--llm", action="store_true", help="尝试调用百炼；失败时自动回退规则 Bot")
    parser.add_argument(
        "--llm-agents",
        type=int,
        help="启用 LLM 的 Agent 数量；未指定时默认为全部玩家",
    )
    parser.add_argument("--model", help="覆盖普通与策略 Agent 的模型，适合短局测试")
    parser.add_argument(
        "--save", default="data/saves/latest_game.json", help="完整管理员存档路径"
    )
    parser.add_argument(
        "--replay", default="data/saves/latest_replay.json", help="公开回放路径"
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    config = load_game_config(args.config)
    if args.seed is not None:
        config.random_seed = args.seed
    if args.model:
        config.normal_agent_model = args.model
        config.strategy_agent_model = args.model
    if config.human_count:
        raise SystemExit("main.py 用于纯自动演示；混合模式请通过 HumanPlayer 后端接口逐阶段控制。")

    engine = GameEngine(config)
    controllers = None
    client = None
    llm_player_ids: list[str] = []
    mode = "规则 Bot"
    if args.llm:
        client = LLMClient()
        llm_agent = LLMAgent(client)
        available_ids = [
            player.id for player in engine.state.players.values() if not player.is_human
        ]
        requested = args.llm_agents if args.llm_agents is not None else len(available_ids)
        if requested < 1 or requested > len(available_ids):
            raise SystemExit(f"--llm-agents 必须在 1 到 {len(available_ids)} 之间")
        llm_player_ids = available_ids[:requested]
        controllers = {player_id: llm_agent for player_id in llm_player_ids}
        mode = f"百炼 LLM {requested} 人 + 规则 Bot（失败自动回退）"
    elif args.llm_agents is not None or args.model:
        raise SystemExit("--llm-agents/--model 需要与 --llm 一起使用")
    AutoGameRunner(engine, controllers).run()
    JSONStorage.save(engine, args.save)
    export_replay(engine, args.replay)

    result = engine.state.result
    output = {
        "mode": mode,
        "seed": config.random_seed,
        "days": engine.state.day,
        "steps": engine.state.step_count,
        "shelter_survived": result.shelter_survived,
        "faction_winner": result.faction_winner,
        "final_resources": {
            "food": engine.state.resources.food,
            "energy": engine.state.resources.energy,
            "medicine": engine.state.resources.medicine,
            "parts": engine.state.resources.parts,
            "stability": engine.state.resources.stability,
        },
        "scores": result.scores,
        "llm_player_ids": llm_player_ids,
        "llm_stats": client.stats.as_dict() if client else None,
        "save": str(Path(args.save).resolve()),
        "public_replay": str(Path(args.replay).resolve()),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
