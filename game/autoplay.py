from __future__ import annotations

from collections.abc import Mapping

from agents.base import AgentController
from agents.fallback import RuleBasedBot
from agents.schemas import AgentDecision
from game.engine import GameEngine
from game.enums import GamePhase, Visibility
from game.exceptions import GameRuleError


class AutoGameRunner:
    """Bounded phase runner: each AI receives at most one decision per phase."""

    def __init__(
        self,
        engine: GameEngine,
        controllers: Mapping[str, AgentController] | None = None,
    ) -> None:
        self.engine = engine
        fallback = RuleBasedBot()
        self.fallback = fallback
        self.controllers: dict[str, AgentController] = {
            player.id: (controllers or {}).get(player.id, fallback)
            for player in engine.state.players.values()
            if not player.is_human
        }
        self._processed: set[tuple[int, GamePhase, str]] = set()

    def process_ai_players(self) -> int:
        """Process current phase without advancing; useful for mixed human games."""
        phase = self.engine.state.phase
        if phase in {GamePhase.EVENT, GamePhase.RESOLUTION, GamePhase.FINISHED}:
            return 0
        if phase == GamePhase.VOTING and not any(
            proposal.created_day == self.engine.state.day
            for proposal in self.engine.state.proposals.values()
        ):
            return 0
        count = 0
        for player_id, controller in self.controllers.items():
            key = (self.engine.state.day, self.engine.state.phase, player_id)
            if key in self._processed or not self.engine.state.players[player_id].is_present:
                continue
            self._processed.add(key)
            if phase == GamePhase.ACTION and not self.engine.get_available_actions(player_id):
                self._safe(self.engine.end_turn, player_id)
                continue
            try:
                decision = controller.decide(self.engine, player_id)
                self._apply_decision(player_id, decision)
            except Exception as exc:  # a single agent can never stall the match
                self.engine._log(
                    "agent_error",
                    f"{player_id} 决策异常，已跳过：{type(exc).__name__}: {exc}",
                    Visibility.ADMIN,
                    [player_id],
                )
            count += 1
        return count

    def reply_to_private_message(
        self,
        receiver_id: str,
        sender_id: str,
        content: str,
    ) -> bool:
        """Send one bounded role-based reply to a human private message."""
        if self.engine.state.phase != GamePhase.DISCUSSION:
            return False
        if receiver_id not in self.controllers:
            return False
        reply = self.fallback.private_reply(self.engine, receiver_id, sender_id, content)
        return self._safe(
            self.engine.send_private_message,
            receiver_id,
            sender_id,
            reply,
        )

    def run(self) -> GameEngine:
        """Run a pure-AI game to completion within the configured max_steps."""
        if any(player.is_human for player in self.engine.state.players.values()):
            raise ValueError("纯自动对局不能包含真人；混合模式请使用 process_ai_players")
        while not self.engine.state.finished:
            self.process_ai_players()
            self.engine.advance_phase()
        return self.engine

    def _apply_decision(self, player_id: str, decision: AgentDecision) -> None:
        phase = self.engine.state.phase
        if phase == GamePhase.DISCUSSION:
            if decision.public_message:
                self._safe(self.engine.send_public_message, player_id, decision.public_message)
            for message in decision.private_messages[:1]:
                self._safe(
                    self.engine.send_private_message,
                    player_id,
                    message.receiver_id,
                    message.content,
                )
            if decision.proposal:
                self._safe(
                    self.engine.propose_plan,
                    player_id,
                    decision.proposal.model_dump(),
                )
            if decision.trade:
                trade = decision.trade
                self._safe(
                    self.engine.propose_trade,
                    player_id,
                    trade.receiver_id,
                    trade.offer,
                    trade.request,
                    is_public=trade.is_public,
                    promise=trade.promise,
                )
        elif phase == GamePhase.ACTION:
            for choice in decision.actions[:2]:
                data = choice.model_dump(exclude={"secret"})
                if choice.secret:
                    self._safe(self.engine.perform_secret_action, player_id, data)
                else:
                    self._safe(self.engine.perform_action, player_id, data)
            self._safe(self.engine.end_turn, player_id)
        elif phase == GamePhase.VOTING:
            for proposal_id, choice in decision.votes.items():
                self._safe(self.engine.vote, player_id, proposal_id, choice)
        elif phase == GamePhase.EXPULSION:
            if decision.expulsion_nomination:
                self._safe(
                    self.engine.nominate_for_expulsion,
                    player_id,
                    decision.expulsion_nomination,
                )
            if decision.defense:
                self._safe(self.engine.submit_defense, player_id, decision.defense)
            if decision.expulsion_vote is not None:
                self._safe(self.engine.vote_expulsion, player_id, decision.expulsion_vote)

    def _safe(self, function: object, *args: object, **kwargs: object) -> bool:
        try:
            function(*args, **kwargs)  # type: ignore[operator]
            return True
        except (GameRuleError, ValueError) as exc:
            self.engine._log(
                "agent_action_rejected",
                f"{getattr(function, '__name__', 'operation')} 被规则拒绝：{exc}",
                Visibility.ADMIN,
            )
            return False


def run_auto_game(
    engine: GameEngine | None = None,
    controllers: Mapping[str, AgentController] | None = None,
) -> GameEngine:
    return AutoGameRunner(engine or GameEngine(), controllers).run()
