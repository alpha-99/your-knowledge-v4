"""
模型客户端 — 统一的 LLM 调用接口

注意：这里 import 的 openai 包是作为**通用客户端**使用，并非只能调用 OpenAI 模型。
DeepSeek、Qwen、智谱等国产大模型都兼容 OpenAI API 格式，因此可以直接复用 openai SDK，
只需在 .env 中配置对应的 base_url 和 api_key 即可切换到不同模型提供商。

所有节点通过此模块调用 LLM，便于统一管理 token 用量和成本。
"""

import ast
import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from tests.cost_guard import CostGuard

load_dotenv()

_cost_guard: CostGuard | None = None


def get_cost_guard() -> CostGuard:
    """获取全局 CostGuard 实例（懒加载），首次调用时创建，后续复用。"""
    global _cost_guard
    if _cost_guard is None:
        budget = float(os.getenv("BUDGET_YUAN", "1.0"))
        _cost_guard = CostGuard(budget_yuan=budget)
    return _cost_guard


def _parse_json_robust(text: str) -> Any:
    """多策略解析 LLM 返回的 JSON，兼容常见格式问题（单引号、尾逗号、代码块）"""
    strategies: list[tuple[str, Any]] = [
        ("direct", text),
    ]

    # 策略 2: 去除 markdown 代码块包裹
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if len(lines) >= 3:
            strategies.append(("strip_codeblock", "\n".join(lines[1:-1])))

    # 策略 3: 修复单引号键名 (Python dict 语法)
    # 将 {'key': value} 转成 {"key": value}
    def fix_single_quotes(s: str) -> str:
        # 替换形如 'key': 的模式为 "key":
        s = re.sub(r"'([^']*)':", r'"\1":', s)
        return s

    for name, candidate in strategies[:]:  # iterate over copy
        strategies.append((f"{name}+fixquotes", fix_single_quotes(candidate)))

    # 策略 4: 所有候选再尝试去掉尾逗号
    for name, candidate in strategies[:]:
        strategies.append((f"{name}+notrail", re.sub(r",\s*([}\]])", r"\1", candidate)))

    last_error = None
    for strategy_name, candidate in strategies:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            continue

    # 最后兜底: ast.literal_eval 处理 Python 字面量语法
    try:
        return ast.literal_eval(text.strip())
    except (ValueError, SyntaxError):
        pass

    raise last_error or ValueError(f"无法解析 JSON: {text[:200]}")


def _extract_json(text: str) -> Any:
    """提取文本中的 JSON 并解析，自动修复常见格式问题"""
    # 尝试提取 markdown 代码块中的 JSON
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if len(lines) >= 3:
            cleaned = "\n".join(lines[1:-1])
    return _parse_json_robust(cleaned)


def get_client() -> OpenAI:
    """获取 OpenAI 兼容客户端（openai SDK 可连接任何兼容 API，不限于 OpenAI）"""
    return OpenAI(
        api_key=os.getenv("LLM_API_KEY", ""),
        base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
    )


def chat(
    prompt: str,
    system: str = "你是一个专业的 AI 技术分析师。",
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    node_name: str = "unknown",
) -> tuple[str, dict]:
    """调用 LLM 并返回 (回复文本, token用量信息)

    Args:
        prompt: 用户 prompt
        system: 系统 prompt
        model: 模型名，默认从环境变量读取
        temperature: 采样温度
        max_tokens: 最大输出 token 数
        node_name: 调用节点名称（用于成本追踪）

    Returns:
        (response_text, usage_dict) 其中 usage_dict 包含 prompt_tokens, completion_tokens
    """
    client = get_client()
    model_name = model or os.getenv("LLM_MODEL", "deepseek-chat")

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    text = response.choices[0].message.content or ""
    usage = {
        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
    }

    cost_guard = get_cost_guard()
    cost_guard.record(node_name, usage, model_name)
    cost_guard.check()

    return text, usage


def chat_json(
    prompt: str,
    system: str = "你是一个专业的 AI 技术分析师。请用 JSON 格式回复。",
    node_name: str = "unknown",
    **kwargs: Any,
) -> tuple[dict | list, dict]:
    """调用 LLM 并解析 JSON 响应

    Returns:
        (parsed_json, usage_dict)

    Raises:
        json.JSONDecodeError: 当 LLM 返回非法 JSON 时
    """
    text, usage = chat(prompt, system=system, node_name=node_name, **kwargs)

    parsed = _extract_json(text)
    return parsed, usage


def accumulate_usage(tracker: dict, new_usage: dict) -> dict:
    """累加 token 用量到 cost_tracker

    Args:
        tracker: 现有的 cost_tracker
        new_usage: 本次调用的 usage_dict

    Returns:
        更新后的 cost_tracker（包含累计 token 数和成本估算）
    """
    prompt = tracker.get("prompt_tokens", 0) + new_usage.get("prompt_tokens", 0)
    completion = tracker.get("completion_tokens", 0) + new_usage.get("completion_tokens", 0)

    # DeepSeek 定价: 输入 ¥1/百万token, 输出 ¥2/百万token（近似）
    input_price = float(os.getenv("PRICE_INPUT_PER_MILLION", "1.0"))
    output_price = float(os.getenv("PRICE_OUTPUT_PER_MILLION", "2.0"))
    total_cost = (prompt * input_price + completion * output_price) / 1_000_000

    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_cost_yuan": round(total_cost, 6),
    }