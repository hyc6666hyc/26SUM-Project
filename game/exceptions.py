class GameRuleError(ValueError):
    """A readable rejection raised when a game rule is violated."""

    def __init__(self, message: str, code: str = "RULE_VIOLATION") -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"ok": "false", "code": self.code, "reason": self.message}

