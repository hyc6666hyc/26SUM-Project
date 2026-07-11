from __future__ import annotations

import json
from pathlib import Path

from game.enums import Role
from game.models import Event


def load_events(path: str | Path | None = None) -> list[Event]:
    """Load validated event definitions from JSON."""
    file_path = Path(path) if path else Path(__file__).resolve().parent.parent / "data" / "events.json"
    raw_events = json.loads(file_path.read_text(encoding="utf-8"))
    events: list[Event] = []
    required = {
        "id",
        "title",
        "description",
        "visible_effect",
        "available_solutions",
        "resource_cost",
        "success_effect",
        "failure_effect",
        "hidden_risk",
        "related_facility",
        "role_bonus",
    }
    for item in raw_events:
        missing = required.difference(item)
        if missing:
            raise ValueError(f"事件 {item.get('id', '<unknown>')} 缺少字段: {sorted(missing)}")
        data = dict(item)
        data["role_bonus"] = Role(data["role_bonus"]) if data.get("role_bonus") else None
        events.append(Event(**data))
    if len(events) < 12:
        raise ValueError("至少需要 12 个事件")
    return events
