from __future__ import annotations

import json
from pathlib import Path

from game.engine import GameEngine
from game.replay import key_events, public_timeline
from services.storage import to_primitive


def export_replay(engine: GameEngine, path: str | Path) -> Path:
    """Export display-safe replay data without private or admin secrets."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timeline": public_timeline(engine),
        "key_events": key_events(engine),
        "result": to_primitive(engine.state.result) if engine.state.result else None,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
