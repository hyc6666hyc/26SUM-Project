from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)
Transport = Callable[[list[dict[str, str]], str, float], str]


@dataclass(slots=True)
class LLMStats:
    """Non-secret telemetry used to control latency and API cost."""

    decisions: int = 0
    requests: int = 0
    successful_decisions: int = 0
    failed_decisions: int = 0
    format_repairs: int = 0
    api_errors: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    total_seconds: float = 0.0
    model_requests: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["total_seconds"] = round(self.total_seconds, 3)
        return data


class LLMClient:
    """One bounded OpenAI-compatible client for all DashScope model calls."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 1,
        transport: Transport | None = None,
    ) -> None:
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:  # pragma: no cover - optional convenience
            pass
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self.base_url = base_url or os.getenv(
            "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.timeout = timeout
        self.max_retries = max(0, min(max_retries, 2))
        self.transport = transport
        self.last_error: str | None = None
        self.stats = LLMStats()

    @property
    def available(self) -> bool:
        return bool(self.api_key or self.transport)

    def generate_structured(
        self, messages: list[dict[str, str]], response_model: type[T], model: str
    ) -> T | None:
        """Validate JSON, request one repair on failure, then return None for fallback."""
        self.stats.decisions += 1
        if not self.available:
            self.last_error = "未配置 DASHSCOPE_API_KEY"
            self.stats.failed_decisions += 1
            return None
        current_messages = list(messages)
        attempts = 2  # first output + exactly one format repair attempt
        for attempt in range(attempts):
            self.stats.requests += 1
            self.stats.model_requests[model] = self.stats.model_requests.get(model, 0) + 1
            started = perf_counter()
            try:
                content, usage = self._request(current_messages, model)
                self.stats.prompt_tokens += usage["prompt_tokens"]
                self.stats.completion_tokens += usage["completion_tokens"]
                self.stats.total_tokens += usage["total_tokens"]
                result = response_model.model_validate_json(content)
                self.stats.successful_decisions += 1
                self.last_error = None
                return result
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                self.last_error = f"结构化输出无效: {exc}"
                if attempt == 0:
                    self.stats.format_repairs += 1
                    current_messages = current_messages + [
                        {
                            "role": "user",
                            "content": "上一条输出未通过 schema 校验。只输出修复后的 JSON，不要附加说明。",
                        }
                    ]
            except Exception as exc:  # network/SDK errors must not stop the match
                self.stats.api_errors += 1
                self.last_error = f"LLM 调用失败: {type(exc).__name__}: {exc}"
                status_code = getattr(exc, "status_code", None)
                if status_code in {400, 401, 403, 404, 422} or attempt >= self.max_retries:
                    break
            finally:
                self.stats.total_seconds += perf_counter() - started
        self.stats.failed_decisions += 1
        return None

    def _request(
        self, messages: list[dict[str, str]], model: str
    ) -> tuple[str, dict[str, int]]:
        if self.transport:
            return self.transport(messages, model, self.timeout), {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency installation error
            raise RuntimeError("缺少 openai，请执行 pip install -r requirements.txt") from exc
        client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
        response = client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
            max_completion_tokens=2000,
            temperature=0.4,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("模型返回空内容")
        usage = response.usage
        return content, {
            "prompt_tokens": int(usage.prompt_tokens or 0) if usage else 0,
            "completion_tokens": int(usage.completion_tokens or 0) if usage else 0,
            "total_tokens": int(usage.total_tokens or 0) if usage else 0,
        }
