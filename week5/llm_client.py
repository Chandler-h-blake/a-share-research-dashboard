"""第五周 LLM 调用封装。

本模块是多 Agent 系统的基础能力，不是增强接口。
第五周研报必须由 LLM 生成；如果没有 API key，程序应直接失败。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    """LLM 调用配置。"""

    provider: str = "openai_compatible"
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str = "https://api.openai.com/v1/chat/completions"
    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    timeout: int = 60


class LLMClient:
    """OpenAI-compatible Chat Completions 客户端。

    可用于 OpenAI、DeepSeek、Qwen 等兼容 Chat Completions 的服务。
    例如使用 DeepSeek 时，可设置：

    - LLM_API_KEY_ENV=DEEPSEEK_API_KEY
    - LLM_BASE_URL=https://api.deepseek.com/chat/completions
    - LLM_MODEL=deepseek-chat
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig(
            api_key_env=os.getenv("LLM_API_KEY_ENV", "OPENAI_API_KEY"),
            base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1/chat/completions"),
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        )

    def is_configured(self) -> bool:
        return bool(os.getenv(self.config.api_key_env))

    def complete(self, prompt: str) -> str:
        """调用兼容 Chat Completions 的模型。"""

        api_key = os.getenv(self.config.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"未设置 {self.config.api_key_env}，无法调用 LLM。"
                "第五周系统不提供规则版降级路径，请先配置 LLM API key。"
            )

        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "messages": [
                {
                    "role": "system",
                    "content": "你是严谨的中文 A 股投研辅助系统，必须基于输入数据回答。",
                },
                {"role": "user", "content": prompt},
            ],
        }
        request = urllib.request.Request(
            self.config.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM 请求失败：{exc}") from exc

        try:
            return str(result["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"LLM 返回格式异常：{result}") from exc


class LangChainClient:
    """LangChain LLM 编排封装。

    这个类只在显式选择 --backend langchain 时使用。LangChain 只负责编排，
    实际分析仍必须由 LLM 完成。
    """

    def __init__(self) -> None:
        try:
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "当前环境未安装 LangChain 相关依赖。"
                "请安装 langchain-core 和 langchain-openai，或使用默认 --backend llm。"
            ) from exc

        self._prompt_cls = ChatPromptTemplate
        self._llm_cls = ChatOpenAI
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.base_url = os.getenv("LLM_BASE_URL") or None

    def complete(self, prompt: str) -> str:
        """使用 LangChain 调用模型。"""

        api_key = os.getenv(os.getenv("LLM_API_KEY_ENV", "OPENAI_API_KEY"))
        if not api_key:
            raise RuntimeError("未设置 LLM API key，无法使用 LangChain backend。")

        llm_kwargs = {
            "model": self.model,
            "temperature": 0.2,
        }
        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

        llm = self._llm_cls(**llm_kwargs)
        prompt_template = self._prompt_cls.from_messages(
            [
                ("system", "你是严谨的中文 A 股投研辅助系统，必须基于输入数据回答。"),
                ("user", "{input}"),
            ]
        )
        chain = prompt_template | llm
        result = chain.invoke({"input": prompt})
        return str(result.content).strip()
