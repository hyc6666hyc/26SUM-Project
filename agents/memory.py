from __future__ import annotations

from game.models import Player


def update_agent_memory(player: Player, memory_update: str, max_items: int = 12) -> None:
    """Store a short displayable summary and bound prompt growth."""
    text = memory_update.strip()[:500]
    if text:
        player.turn_memory.append(text)
        player.key_memory.append(text)
        player.key_memory[:] = player.key_memory[-max_items:]

