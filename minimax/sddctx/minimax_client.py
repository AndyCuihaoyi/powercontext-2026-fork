"""MiniMax 客户端：OpenAI 兼容 `POST {base}/chat/completions`，只用标准库。

密钥只从环境变量 `MINIMAX_API_KEY` 读取，绝不写入仓库、日志或文档
（题面要求配置示例只能用占位值）。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from . import config

SYSTEM_PROMPT = (
    "你是一名严格遵循规格驱动开发（SDD）的工程师。"
    "只依据用户提供的上下文包（规格 / 现有代码 / 测试 / 任务状态）完成任务，"
    "不得修改规格与测试，只能修改实现代码。\n"
    "输出协议：对每个需要修改的文件，输出一个整文件块，格式严格为\n"
    "<<<FILE 相对路径>>>\n（文件完整内容）\n<<<END FILE>>>\n"
    "相对路径必须以 demo_project/app/ 开头；不要输出 diff；不要输出未改动的文件。"
)


class MiniMaxError(RuntimeError):
    pass


def configured() -> bool:
    return config.minimax_configured()


def chat(
    messages: list[dict[str, str]],
    *,
    model: str = "",
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """一次真实调用；返回内容 + 用量 + 原始响应，供开发记录落盘。"""

    if not configured():
        raise MiniMaxError(
            "未设置 MINIMAX_API_KEY。请 export MINIMAX_API_KEY=<你的密钥> 后重试，"
            "或用 --replay 复现已记录的响应。"
        )
    payload = {
        "model": model or config.MINIMAX_MODEL,
        "messages": messages,
        "temperature": config.MINIMAX_TEMPERATURE if temperature is None else temperature,
        "max_tokens": config.MINIMAX_MAX_TOKENS if max_tokens is None else max_tokens,
        "stream": False,
    }
    request = urllib.request.Request(
        f"{config.MINIMAX_BASE_URL}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.MINIMAX_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=config.MINIMAX_TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8"))
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise MiniMaxError(f"MiniMax HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise MiniMaxError(f"MiniMax 网络不可达：{exc.reason}") from exc
    elapsed = int((time.perf_counter() - started) * 1000)

    choices = body.get("choices") or []
    if status != 200 or not choices:
        code = body.get("base_resp") or body.get("code") or ""
        raise MiniMaxError(f"MiniMax 响应异常（status={status}, code={code}）：{json.dumps(body)[:800]}")
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if not content.strip():
        # 推理型模型（如 M3.1-Flash）在小 max_tokens 下只吐 reasoning_content，正文被截断
        raise MiniMaxError(
            "MiniMax 返回空正文（reasoning 模型请提高 MINIMAX_MAX_TOKENS）："
            f"finish_reason={choices[0].get('finish_reason')} usage={json.dumps(body.get('usage') or {})[:200]} "
            f"reasoning_len={len(message.get('reasoning_content') or '')}"
        )
    return {
        "model": body.get("model", payload["model"]),
        "content": content,
        "usage": body.get("usage") or {},
        "finish_reason": choices[0].get("finish_reason", ""),
        "request_id": body.get("id", ""),
        "elapsed_ms": elapsed,
        "endpoint": f"{config.MINIMAX_BASE_URL}/chat/completions",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "response": body,
    }
