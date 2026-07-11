from __future__ import annotations

from pathlib import Path
import os
from typing import Any

from game.models import GameConfig


def load_game_config(path: str | Path = "config/game_config.yaml") -> GameConfig:
    """Load a YAML config while keeping defaults for omitted fields."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dependency installation error
        raise RuntimeError("缺少 PyYAML，请先执行 pip install -r requirements.txt") from exc

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:  # pragma: no cover - optional convenience
        pass
    file_path = Path(path)
    data: dict[str, Any] = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    env_models = {
        "normal_agent_model": os.getenv("NORMAL_AGENT_MODEL"),
        "strategy_agent_model": os.getenv("STRATEGY_AGENT_MODEL"),
        "review_model": os.getenv("REVIEW_MODEL"),
    }
    data.update({key: value for key, value in env_models.items() if value})
    return GameConfig(**data)
