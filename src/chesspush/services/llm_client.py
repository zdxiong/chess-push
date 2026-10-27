"""qwen3.5-4b LLM 客户端（vLLM / OpenAI 兼容，默认 http://localhost:8000/v1）。

- 模型名自动从 /v1/models 探测（config.llm.model 为空时）。
- 连接失败时按配置降级：strict 抛错 / fallback 返回 None（由上层用规则解说兜底）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests


class LLMClient:
    def __init__(
        self,
        base_url: str,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 256,
        timeout: float = 60.0,
        on_unavailable: str = "fallback",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.on_unavailable = on_unavailable
        self._resolved_model: Optional[str] = None
        self._resolved_done = False

    def list_models(self) -> List[str]:
        try:
            r = requests.get(f"{self.base_url}/models", timeout=min(self.timeout, 3))
            r.raise_for_status()
            data = r.json()
            ids = [m.get("id") for m in data.get("data", [])]
            return [i for i in ids if i]
        except Exception:
            return []

    def resolve_model(self) -> Optional[str]:
        """确定要使用的模型名。配置为空时从服务探测（结果缓存，避免重复卡顿）。"""
        if self._resolved_done:
            return self._resolved_model
        if self.model:
            self._resolved_model = self.model
            self._resolved_done = True
            return self._resolved_model
        models = self.list_models()
        self._resolved_model = models[0] if models else None
        self._resolved_done = True
        return self._resolved_model

    def chat(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """调用 /v1/chat/completions，返回回复文本。失败返回 None（上层降级）。"""
        model = self.resolve_model()
        if model is None:
            if self.on_unavailable == "strict":
                raise ConnectionError("无法确定 LLM 模型名，且配置要求 strict")
            return None
        payload = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        try:
            r = requests.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            return (data["choices"][0]["message"]["content"] or "").strip()
        except Exception:
            if self.on_unavailable == "strict":
                raise
            return None
