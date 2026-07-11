from __future__ import annotations

from dataclasses import dataclass

from agents.human_player import HumanPlayer
from agents.llm_agent import LLMAgent
from game.autoplay import AutoGameRunner
from game.engine import GameEngine
from game.models import GameConfig
from services.llm_client import LLMClient


@dataclass(slots=True)
class GameSession:
    """UI-owned handles; all numeric rules remain inside GameEngine."""

    engine: GameEngine
    runner: AutoGameRunner
    mode: str
    human: HumanPlayer | None = None
    llm_client: LLMClient | None = None
    llm_player_ids: list[str] | None = None
    auto_running: bool = False

    @property
    def viewer_id(self) -> str:
        return self.human.player_id if self.human else next(iter(self.engine.state.players))

    def advance_once(self) -> None:
        if self.engine.state.finished:
            self.auto_running = False
            return
        self.runner.process_ai_players()
        self.engine.advance_phase()
        if self.engine.state.finished:
            self.auto_running = False

    def send_public_message(self, content: str) -> int:
        """Send the human message and run the one bounded AI discussion turn."""
        if not self.human:
            raise ValueError("当前对局没有真人玩家")
        self.human.speak(content)
        return self.runner.process_ai_players()

    def send_private_message(self, receiver_id: str, content: str) -> bool:
        """Send a private message and request one immediate bounded AI reply."""
        if not self.human:
            raise ValueError("当前对局没有真人玩家")
        self.human.private_message(receiver_id, content)
        return self.runner.reply_to_private_message(
            receiver_id,
            self.human.player_id,
            content,
        )


def build_game_session(
    *,
    mode: str,
    player_count: int = 6,
    total_days: int = 6,
    random_seed: int = 42,
    enable_saboteur: bool = True,
    use_llm: bool = False,
    llm_agents: int = 1,
    auto_advance_delay: float = 0.8,
) -> GameSession:
    """Construct a pure-AI or one-human match without importing Streamlit."""
    if mode not in {"ai", "human"}:
        raise ValueError("mode 必须为 ai 或 human")
    config = GameConfig(
        player_count=player_count,
        human_count=1 if mode == "human" else 0,
        total_days=total_days,
        enable_saboteur=enable_saboteur,
        random_seed=random_seed,
        auto_advance_delay=auto_advance_delay,
        max_steps=max(200, total_days * 7),
    )
    engine = GameEngine(config)
    ai_ids = [player.id for player in engine.state.players.values() if not player.is_human]
    controllers = None
    client = None
    llm_player_ids: list[str] = []
    if use_llm:
        client = LLMClient()
        if not client.available:
            raise ValueError("未在 .env 中配置 DASHSCOPE_API_KEY")
        count = max(1, min(llm_agents, len(ai_ids)))
        llm_player_ids = ai_ids[:count]
        llm_agent = LLMAgent(client)
        controllers = {player_id: llm_agent for player_id in llm_player_ids}
    runner = AutoGameRunner(engine, controllers)
    human = HumanPlayer(engine, "player_1") if mode == "human" else None
    return GameSession(
        engine=engine,
        runner=runner,
        mode=mode,
        human=human,
        llm_client=client,
        llm_player_ids=llm_player_ids,
    )
