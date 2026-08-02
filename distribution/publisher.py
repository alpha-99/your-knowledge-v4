"""推送模块 — 将格式化后的内容通过各类渠道分发。

纯 Python + aiohttp 实现，不引入第三方框架。
"""

from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import aiohttp

from distribution.formatter import generate_daily_digest

logger = logging.getLogger(__name__)

_TELEGRAM_API_BASE = "https://api.telegram.org"


@dataclass
class PublishResult:
    """记录每次发布操作的结果。

    Attributes:
        channel: 发布渠道名称，如 ``"telegram"`` 或 ``"feishu"``。
        success: 发布是否成功。
        message_id: 成功时返回的消息 ID，失败时为 None。
        error: 失败时的错误信息，成功时为 None。
    """

    channel: str
    success: bool
    message_id: str | None = None
    error: str | None = None


class BasePublisher(ABC):
    """发布器抽象基类。

    所有渠道发布器必须实现 ``send_message()`` 和 ``send_digest()``。
    """

    @abstractmethod
    async def send_message(self, content: str) -> PublishResult:
        """发送单条文本消息。

        Args:
            content: 消息文本。

        Returns:
            PublishResult 记录发布结果。
        """

    @abstractmethod
    async def send_digest(self, digest: dict[str, Any]) -> list[PublishResult]:
        """发送简报。

        Args:
            digest: ``generate_daily_digest()`` 返回的 dict，
                包含 ``markdown`` / ``telegram`` / ``feishu`` 三个字段。

        Returns:
            每次推送结果的列表。
        """


class TelegramPublisher(BasePublisher):
    """Telegram 推送器，通过 Bot API 发送 MarkdownV2 消息。

    必需环境变量：
        * ``TELEGRAM_BOT_TOKEN`` — Telegram Bot Token
        * ``TELEGRAM_CHAT_ID`` — 目标对话 ID

    HTTP 请求超时：30 秒。
    """

    def __init__(self) -> None:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            raise ValueError(
                "环境变量 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID 必须同时设置"
            )
        self._token: str = token
        self._chat_id: str = chat_id

    @property
    def _api_url(self) -> str:
        return f"{_TELEGRAM_API_BASE}/bot{self._token}/sendMessage"

    async def send_message(self, content: str) -> PublishResult:
        """通过 Telegram Bot API 发送一条 MarkdownV2 消息。

        Args:
            content: 已按 MarkdownV2 转义的文本。

        Returns:
            PublishResult 对象。
        """
        payload: dict[str, str] = {
            "chat_id": self._chat_id,
            "text": content,
            "parse_mode": "MarkdownV2",
        }
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            ) as session:
                async with session.post(self._api_url, json=payload) as resp:
                    data: dict[str, Any] = await resp.json()
                    if resp.status == 200 and data.get("ok"):
                        message_id = str(data["result"]["message_id"])
                        return PublishResult(
                            channel="telegram", success=True, message_id=message_id
                        )
                    error_msg = data.get("description", f"HTTP {resp.status}")
                    return PublishResult(
                        channel="telegram", success=False, error=error_msg
                    )
        except aiohttp.ClientError as exc:
            return PublishResult(
                channel="telegram", success=False, error=str(exc)
            )

    async def send_digest(self, digest: dict[str, Any]) -> list[PublishResult]:
        """发送 Telegram 格式简报摘要。

        Args:
            digest: 包含 ``telegram`` 字段的简报 dict。

        Returns:
            包含单个结果的列表。
        """
        content: str = digest.get("telegram", "")
        if not content:
            return [
                PublishResult(
                    channel="telegram", success=True, error="无内容可发送"
                )
            ]
        result = await self.send_message(content)
        return [result]


class FeishuPublisher(BasePublisher):
    """飞书推送器，通过 Webhook 发送交互式卡片消息。

    必需环境变量：
        * ``FEISHU_WEBHOOK_URL`` — 飞书自定义机器人 Webhook 地址

    可选环境变量：
        * ``FEISHU_RATE_LIMIT_SEC`` — 卡片之间的最小间隔（秒），默认 0.5
        * ``FEISHU_MAX_CONCURRENT`` — 最大并发数，默认 1

    HTTP 请求超时：30 秒。
    """

    def __init__(self) -> None:
        webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
        if not webhook_url:
            raise ValueError("环境变量 FEISHU_WEBHOOK_URL 未设置")
        self._webhook_url: str = webhook_url
        self._rate_limit_sec: float = float(os.getenv("FEISHU_RATE_LIMIT_SEC", "0.5"))
        self._max_concurrent: int = int(os.getenv("FEISHU_MAX_CONCURRENT", "1"))
        self._semaphore = asyncio.Semaphore(self._max_concurrent)

    async def send_message(self, content: str) -> PublishResult:
        """飞书 Webhook 不支持裸文本，此方法将文本包装为 simple 卡片。

        Args:
            content: 纯文本消息内容。

        Returns:
            PublishResult 对象。
        """
        card: dict[str, Any] = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "知识简报"},
                    "template": "blue",
                },
                "elements": [
                    {"tag": "markdown", "content": content},
                ],
            },
        }
        return await self._post_card(card)

    async def _post_card(self, card: dict[str, Any]) -> PublishResult:
        """向飞书 Webhook 发送一张卡片。

        Args:
            card: 飞书卡片消息 dict，包含 ``msg_type`` 和 ``card`` 字段。

        Returns:
            PublishResult 对象。
        """
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            ) as session:
                async with session.post(self._webhook_url, json=card) as resp:
                    data: dict[str, Any] = await resp.json()
                    if resp.status == 200 and data.get("code") == 0:
                        return PublishResult(channel="feishu", success=True)
                    error_msg = data.get("msg", f"HTTP {resp.status}")
                    return PublishResult(
                        channel="feishu", success=False, error=error_msg
                    )
        except aiohttp.ClientError as exc:
            return PublishResult(
                channel="feishu", success=False, error=str(exc)
            )

    async def _post_card_throttled(self, card: dict[str, Any]) -> PublishResult:
        """带限流的卡片发送：信号量控制并发 + 间隔控制频率。

        Args:
            card: 飞书卡片消息 dict。

        Returns:
            PublishResult 对象。
        """
        async with self._semaphore:
            result = await self._post_card(card)
            await asyncio.sleep(self._rate_limit_sec)
            return result

    async def send_digest(self, digest: dict[str, Any]) -> list[PublishResult]:
        """发送飞书格式简报摘要。

        每篇文章对应一张独立卡片，按 ``FEISHU_MAX_CONCURRENT``
        和 ``FEISHU_RATE_LIMIT_SEC`` 限流串行/半串行发送。

        Args:
            digest: 包含 ``feishu`` 字段的简报 dict，
                该字段为 ``json_to_feishu()`` 输出的 card dict 列表。

        Returns:
            每张卡片的推送结果列表。
        """
        cards: list[dict[str, Any]] = digest.get("feishu", [])
        if not cards:
            return [
                PublishResult(
                    channel="feishu", success=True, error="无内容可发送"
                )
            ]
        tasks = [self._post_card_throttled(card) for card in cards]
        return list(await asyncio.gather(*tasks))


async def publish_daily_digest(
    knowledge_dir: str = "knowledge/articles",
    date: str | None = None,
    top_n: int = 5,
    channels: list[str] | None = None,
) -> list[PublishResult]:
    """生成并发布当日知识简报到所选渠道（并发）。

    工作流：
        1. 调用 ``generate_daily_digest()`` 生成三种格式
        2. 为每个渠道初始化对应的 Publisher
        3. 并发发布到所有选定的渠道

    Args:
        knowledge_dir: 知识条目 JSON 文件所在目录。
        date: ISO 格式日期字符串（如 ``"2026-07-30"``），None 表示今天（UTC）。
        top_n: 每个 category 中保留的文章数。
        channels: 要发布的渠道名列表。可选 ``"telegram"`` / ``"feishu"``。
            None 表示发布到所有已配置渠道。

    Returns:
        所有渠道所有操作的 PublishResult 列表。
    """
    digest = generate_daily_digest(
        knowledge_dir=knowledge_dir, date=date, top_n=top_n
    )

    if channels is None:
        channels = ["telegram", "feishu"]

    publishers: dict[str, TelegramPublisher | FeishuPublisher] = {}
    for channel in channels:
        try:
            if channel == "telegram":
                publishers[channel] = TelegramPublisher()
            elif channel == "feishu":
                publishers[channel] = FeishuPublisher()
            else:
                logger.warning("未知渠道 %s，已跳过", channel)
        except ValueError as exc:
            logger.warning("渠道 %s 初始化失败: %s", channel, exc)

    coros = {}
    for channel, pub in publishers.items():
        coros[channel] = pub.send_digest(digest)

    results: list[PublishResult] = []
    gathered = await asyncio.gather(*coros.values(), return_exceptions=True)
    for channel, result_or_exc in zip(coros.keys(), gathered):
        if isinstance(result_or_exc, Exception):
            logger.error("渠道 %s 执行异常: %s", channel, result_or_exc)
            results.append(
                PublishResult(
                    channel=channel, success=False, error=str(result_or_exc)
                )
            )
        else:
            results.extend(result_or_exc)

    return results
