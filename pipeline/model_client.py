"""
模型客户端 — 流水线版本（V2 遗留）

V3 中推荐使用 workflows/model_client.py，此文件保持向后兼容。
"""

# 直接复用 workflows 版本
from workflows.model_client import (  # noqa: F401
    accumulate_usage,
    chat,
    chat_json,
    get_client,
)