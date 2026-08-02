"""
知识库交互模块 — Bot 核心逻辑

提供知识搜索、用户订阅管理和权限控制功能。
基于规则匹配的意图识别，不依赖 LLM 调用。
"""

from __future__ import annotations

import json
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any


# ======================================================================
# 枚举定义
# ======================================================================


class Intent(Enum):
    """用户意图类型"""

    SEARCH = "search"
    TODAY = "today"
    TOP = "top"
    SUBSCRIBE = "subscribe"
    HELP = "help"
    UNKNOWN = "unknown"


class Permission(Enum):
    """权限级别

    语义说明：
        READ:   可查看、搜索知识条目
        WRITE:  可管理订阅标签（包含 READ）
        DELETE: 可删除知识条目（包含 READ + WRITE）
    """

    READ = "read"
    WRITE = "write"
    DELETE = "delete"


# ======================================================================
# 意图识别
# ======================================================================

_COMMAND_PREFIXES: list[tuple[str, Intent]] = [
    ("/search", Intent.SEARCH),
    ("/today", Intent.TODAY),
    ("/top", Intent.TOP),
    ("/subscribe", Intent.SUBSCRIBE),
    ("/help", Intent.HELP),
]

_NATURAL_LANGUAGE_PATTERNS: list[tuple[list[str], Intent]] = [
    (
        ["搜索", "查询", "查找", "找一下", "搜", "search", "find", "有哪些", "有没有"],
        Intent.SEARCH,
    ),
    (
        ["今天", "今日", "简报", "日报", "最新", "today", "daily", "今日汇总", "今日摘要"],
        Intent.TODAY,
    ),
    (
        ["热门", "排行", "top", "推荐", "trending", "最热", "热点", "评分最高", "高评分"],
        Intent.TOP,
    ),
    (
        ["订阅", "关注", "追踪", "subscribe", "follow"],
        Intent.SUBSCRIBE,
    ),
    (
        [
            "帮助", "help", "怎么", "功能", "用法", "使用",
            "指南", "说明", "指令", "命令", "代码", "菜单",
        ],
        Intent.HELP,
    ),
]


def recognize_intent(text: str) -> tuple[Intent, str]:
    """意图识别 — 基于规则匹配，不使用 LLM。

    优先级：命令前缀 > 自然语言关键词。

    Args:
        text: 用户输入的原始文本。

    Returns:
        (Intent, 参数字符串) 元组。参数字符串为去除命令前缀后的剩余文本，
        或于自然语言匹配时为完整输入文本。
    """
    text_stripped = text.strip()
    text_lower = text_stripped.lower()

    for prefix, intent in _COMMAND_PREFIXES:
        if text_lower.startswith(prefix):
            args = text_stripped[len(prefix) :].strip()
            return (intent, args)

    for keywords, intent in _NATURAL_LANGUAGE_PATTERNS:
        if any(kw in text_stripped for kw in keywords):
            return (intent, text_stripped)

    return (Intent.UNKNOWN, text_stripped)


# ======================================================================
# KnowledgeSearchEngine — 搜索引擎
# ======================================================================


class KnowledgeSearchEngine:
    """知识库搜索引擎，支持关键词、标签、日期范围过滤。

    从 knowledge/articles/ 目录加载所有 JSON 文章，
    提供多条件组合搜索能力。

    Attributes:
        articles: 已加载的全部文章列表，每个元素为 {id, title, url, tags, ...}。
    """

    def __init__(self, knowledge_dir: str = "") -> None:
        """初始化搜索引擎并加载文章。

        Args:
            knowledge_dir: 知识库目录路径，默认为项目根目录下的
                knowledge/articles/。
        """
        if not knowledge_dir:
            knowledge_dir = str(
                Path(__file__).parent.parent / "knowledge" / "articles"
            )
        self._articles_dir = Path(knowledge_dir)
        self.articles: list[dict[str, Any]] = []
        self._load()

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """从知识库目录扫描并加载所有 JSON 文章文件。"""
        self.articles = []
        if not self._articles_dir.exists():
            return
        for filepath in sorted(self._articles_dir.glob("*.json")):
            if filepath.name == "index.json":
                continue
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    article = json.load(f)
                    self.articles.append(article)
            except (json.JSONDecodeError, OSError):
                pass

    def reload(self) -> None:
        """重新加载文章列表（数据更新后调用）。"""
        self._load()

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------

    def search(
        self,
        keyword: str = "",
        tags: list[str] | None = None,
        date_from: str = "",
        date_to: str = "",
        category: str = "",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """按多种条件组合搜索知识条目。

        所有过滤条件之间为 AND 逻辑；符合条件的文章按
        relevance_score 降序排列，返回前 limit 条。

        Args:
            keyword: 搜索关键词，在 title/summary/tags/key_insight
                各字段中进行不区分大小写的子串匹配。
            tags: 按标签过滤，文章需包含列表中所有标签（不区分大小写）。
                传 None 或空列表表示不限制。
            date_from: 起始日期，格式 YYYY-MM-DD。
            date_to: 截止日期，格式 YYYY-MM-DD。
            category: 按分类过滤，精确匹配（不区分大小写）。
            limit: 返回结果数量上限。

        Returns:
            按 relevance_score 降序的搜索结果列表。
        """
        results: list[dict[str, Any]] = []
        keyword_lower = keyword.lower() if keyword else ""

        for article in self.articles:
            if keyword_lower and not self._match_keyword(article, keyword_lower):
                continue
            if tags and not self._match_tags(article, tags):
                continue
            if (date_from or date_to) and not self._match_date_range(
                article, date_from, date_to
            ):
                continue
            if category and article.get("category", "").lower() != category.lower():
                continue
            results.append(article)

        results.sort(key=lambda a: a.get("relevance_score", 0), reverse=True)
        return results[:limit]

    def get_today_articles(self, limit: int = 20) -> list[dict[str, Any]]:
        """获取今日采集的文章。

        Args:
            limit: 返回数量上限。

        Returns:
            今日文章列表。
        """
        today_str = date.today().isoformat()
        return self.search(date_from=today_str, date_to=today_str, limit=limit)

    def get_top_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取评分最高的文章。

        Args:
            limit: 返回数量上限。

        Returns:
            评分最高的文章列表。
        """
        sorted_articles = sorted(
            self.articles, key=lambda a: a.get("relevance_score", 0), reverse=True
        )
        return sorted_articles[:limit]

    # ------------------------------------------------------------------
    # 内部匹配方法
    # ------------------------------------------------------------------

    @staticmethod
    def _match_keyword(article: dict[str, Any], keyword: str) -> bool:
        """在文章的标题、摘要、关键洞察、标签中匹配关键词。

        Args:
            article: 文章字典。
            keyword: 已转为小写的关键词。

        Returns:
            是否匹配到关键词。
        """
        text_fields = [
            article.get("title", ""),
            article.get("summary", ""),
            article.get("key_insight", ""),
            " ".join(article.get("tags", [])),
        ]
        combined = " ".join(text_fields).lower()
        return keyword in combined

    @staticmethod
    def _match_tags(article: dict[str, Any], tags: list[str]) -> bool:
        """检查文章是否包含所有指定标签。

        Args:
            article: 文章字典。
            tags: 需要匹配的标签列表。

        Returns:
            是否包含所有指定标签。
        """
        article_tags = {t.lower() for t in article.get("tags", [])}
        return all(tag.lower() in article_tags for tag in tags)

    @staticmethod
    def _match_date_range(
        article: dict[str, Any], date_from: str, date_to: str
    ) -> bool:
        """检查文章采集日期是否在指定范围内。

        Args:
            article: 文章字典。
            date_from: 起始日期字符串。
            date_to: 截止日期字符串。

        Returns:
            日期是否在范围内。
        """
        collected = article.get("collected_at", "")
        if not collected:
            return False
        article_date_str = collected[:10]
        if date_from and article_date_str < date_from:
            return False
        if date_to and article_date_str > date_to:
            return False
        return True


# ======================================================================
# SubscriptionManager — 订阅管理
# ======================================================================


class SubscriptionManager:
    """用户订阅管理器，支持增、删、查操作。

    订阅数据以 {user_id: [tag, ...]} 格式持久化到本地 JSON 文件。
    重复添加同一标签会被静默忽略。

    Attributes:
        data_file: 订阅数据文件路径。
    """

    def __init__(self, data_file: str = "") -> None:
        """初始化订阅管理器。

        Args:
            data_file: 订阅数据文件路径，默认为 bot/ 目录下的
                subscriptions.json。
        """
        if not data_file:
            data_file = str(Path(__file__).parent / "subscriptions.json")
        self.data_file = Path(data_file)
        self._subscriptions: dict[str, list[str]] = {}
        self._load()

    def _load(self) -> None:
        """从文件加载订阅数据，文件不存在或损坏时回退为空字典。"""
        if self.data_file.exists():
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    self._subscriptions = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._subscriptions = {}
        else:
            self._subscriptions = {}

    def _save(self) -> None:
        """将当前订阅数据写回文件。"""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(self._subscriptions, f, ensure_ascii=False, indent=2)

    def add_subscription(self, user_id: str, tag: str) -> None:
        """为用户添加一则订阅标签。

        Args:
            user_id: 用户 ID。
            tag: 订阅标签名称。
        """
        tags: list[str] = self._subscriptions.setdefault(user_id, [])
        if tag not in tags:
            tags.append(tag)
            self._save()

    def remove_subscription(self, user_id: str, tag: str) -> None:
        """为用户移除一则订阅标签。

        如果移除后该用户无任何订阅，同时清理其记录。

        Args:
            user_id: 用户 ID。
            tag: 要移除的标签名称。
        """
        if user_id not in self._subscriptions:
            return
        tags = self._subscriptions[user_id]
        if tag in tags:
            tags.remove(tag)
            if not tags:
                del self._subscriptions[user_id]
            self._save()

    def get_user_subscriptions(self, user_id: str) -> list[str]:
        """获取用户的全部订阅标签。

        Args:
            user_id: 用户 ID。

        Returns:
            标签列表，未订阅时返回空列表。
        """
        return self._subscriptions.get(user_id, [])

    def get_all_subscriptions(self) -> dict[str, list[str]]:
        """获取全部用户的订阅数据快照。

        Returns:
            {user_id: [tag, ...]} 字典。
        """
        return dict(self._subscriptions)


# ======================================================================
# PermissionManager — 权限控制
# ======================================================================


_DEFAULT_PERMISSIONS: dict[str, str] = {
    "admin": "delete",
}

_PERMISSION_RANK: dict[Permission, int] = {
    Permission.READ: 0,
    Permission.WRITE: 1,
    Permission.DELETE: 2,
}


class PermissionManager:
    """三级权限控制器，管理用户的 READ / WRITE / DELETE 权限。

    权限具有包含关系：DELETE ⊃ WRITE ⊃ READ。
    未在权限文件中显式配置的用户默认拥有 READ 权限。
    admin 用户默认拥有 DELETE 权限。

    Attributes:
        data_file: 权限数据文件路径。
    """

    def __init__(self, data_file: str = "") -> None:
        """初始化权限管理器。

        Args:
            data_file: 权限数据文件路径，默认为 bot/ 目录下的
                permissions.json。
        """
        if not data_file:
            data_file = str(Path(__file__).parent / "permissions.json")
        self.data_file = Path(data_file)
        self._permissions: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        """从文件加载权限数据，不存在或损坏时回退到默认值。"""
        if self.data_file.exists():
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    self._permissions = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._permissions = {**_DEFAULT_PERMISSIONS}
        else:
            self._permissions = {**_DEFAULT_PERMISSIONS}

    def _save(self) -> None:
        """将当前权限数据写回文件。"""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(self._permissions, f, ensure_ascii=False, indent=2)

    def get_permission(self, user_id: str) -> Permission:
        """获取用户的当前权限级别。

        未显式配置的用户默认返回 Permission.READ。

        Args:
            user_id: 用户 ID。

        Returns:
            用户的权限级别枚举值。
        """
        perm_str = self._permissions.get(user_id, "read")
        try:
            return Permission(perm_str)
        except ValueError:
            return Permission.READ

    def check(self, user_id: str, required: Permission) -> bool:
        """检查用户是否满足指定的权限要求。

        由于权限包含关系，持有 WRITE 权限的用户自动满足 READ 检查。

        Args:
            user_id: 用户 ID。
            required: 所需的最小权限。

        Returns:
            True 表示权限满足。
        """
        current = self.get_permission(user_id)
        return _PERMISSION_RANK.get(current, 0) >= _PERMISSION_RANK.get(required, 0)

    def grant(self, user_id: str, permission: Permission) -> None:
        """授予用户指定权限级别，覆盖原有权限。

        Args:
            user_id: 用户 ID。
            permission: 要授予的权限。
        """
        self._permissions[user_id] = permission.value
        self._save()

    def revoke(self, user_id: str) -> None:
        """撤销用户的自定义权限，恢复为默认 READ 级别。

        Admin 用户的默认权限不会被撤销。

        Args:
            user_id: 用户 ID。
        """
        if user_id in self._permissions and user_id not in _DEFAULT_PERMISSIONS:
            del self._permissions[user_id]
            self._save()


# ======================================================================
# 公开工具函数 — 搜索参数解析 & 结果格式化
# ======================================================================


def parse_search_args(args: str) -> dict[str, Any]:
    """解析搜索参数字符串，提取过滤条件和关键词。

    支持的特殊前缀：
        tag:<标签> 或 #<标签> → 按标签过滤
        cat:<分类> 或 @<分类> → 按分类过滤
        from:<日期> (YYYY-MM-DD) → 起始日期
        to:<日期> (YYYY-MM-DD)   → 截止日期
        其余文本合并为搜索关键词

    Args:
        args: 原始搜索参数字符串。

    Returns:
        包含 keyword, tags, category, date_from, date_to 键的字典。
    """
    tags: list[str] = []
    category = ""
    date_from = ""
    date_to = ""
    keyword_parts: list[str] = []

    for token in args.split():
        if token.startswith("tag:") and len(token) > 4:
            tags.append(token[4:])
        elif token.startswith("#") and len(token) > 1:
            tags.append(token[1:])
        elif token.startswith("cat:") and len(token) > 4:
            category = token[4:]
        elif token.startswith("@") and len(token) > 1:
            category = token[1:]
        elif token.startswith("from:") and len(token) > 5:
            date_from = token[5:]
        elif token.startswith("to:") and len(token) > 3:
            date_to = token[3:]
        else:
            keyword_parts.append(token)

    return {
        "keyword": " ".join(keyword_parts),
        "tags": tags if tags else None,
        "category": category,
        "date_from": date_from,
        "date_to": date_to,
    }


def format_search_results(
    results: list[dict[str, Any]],
    keyword: str = "",
    query: str = "",
    title: str = "",
) -> str:
    """将搜索结果列表格式化为可读的多行文本。

    Args:
        results: 搜索结果文章列表。
        keyword: 触发本次搜索的关键词（用于无结果时的提示）。
        query: keyword 的别名参数，优先使用。
        title: 自定义标题，为空时自动生成。

    Returns:
        格式化的搜索结果文本。
    """
    keyword = query or keyword

    if not results:
        keyword_hint = f'（关键词："{keyword}"）' if keyword else ""
        return f"未找到匹配结果。{keyword_hint}"

    header = title or (
        f'搜索结果（"{keyword}"）' if keyword else "搜索结果"
    )
    lines = [f"{header}，共 {len(results)} 条：\n"]

    for i, article in enumerate(results, 1):
        score = article.get("relevance_score", 0)
        star_count = min(int(score * 5), 5)
        star = "★" * star_count + "☆" * (5 - star_count)

        lines.append(
            f"{i}. {article.get('title', 'N/A')}  [{star} {score:.2f}]"
        )

        summary = article.get("summary", "")
        if summary:
            tail = "..." if len(summary) > 120 else ""
            lines.append(f"   摘要：{summary[:120]}{tail}")

        tags = article.get("tags", [])
        if tags:
            lines.append(f"   标签：{', '.join(tags)}")

        category = article.get("category", "")
        if category:
            lines.append(f"   分类：{category}")

        url = article.get("url", "")
        if url:
            lines.append(f"   链接：{url}")

    return "\n".join(lines)


# ======================================================================
# KnowledgeBot — 主入口
# ======================================================================

_HELP_TEXT = """\
可用命令：

/search <关键词> — 搜索知识库
    支持附加过滤:  tag:<标签>  #<标签>  cat:<分类>  @<分类>
                    from:<日期>  to:<日期>
    示例: /search langchain tag:agent

/today — 查看今日文章
/top [数量] — 查看评分最高的文章

/subscribe — 管理订阅标签
    /subscribe                — 查看当前订阅
    /subscribe add <标签>     — 添加订阅标签
    /subscribe remove <标签>  — 移除订阅标签

/help — 显示此帮助信息"""


class KnowledgeBot:
    """知识库交互 Bot 主入口，整合搜索、订阅和权限控制模块。

    通过 handle_message 提供统一的消息处理入口，自动识别用户意图
    并分发到对应的处理器，同时实施权限校验。

    Attributes:
        search_engine: KnowledgeSearchEngine 实例。
        subscription_manager: SubscriptionManager 实例。
        permission_manager: PermissionManager 实例。
    """

    def __init__(
        self,
        knowledge_dir: str = "",
        subscription_file: str = "",
        permission_file: str = "",
    ) -> None:
        """初始化 KnowledgeBot 及全部子模块。

        Args:
            knowledge_dir: 知识库目录路径，默认 knowledge/articles/。
            subscription_file: 订阅数据文件路径，默认 bot/subscriptions.json。
            permission_file: 权限数据文件路径，默认 bot/permissions.json。
        """
        self.search_engine = KnowledgeSearchEngine(knowledge_dir)
        self.subscription_manager = SubscriptionManager(subscription_file)
        self.permission_manager = PermissionManager(permission_file)

    # ------------------------------------------------------------------
    # 统一消息入口
    # ------------------------------------------------------------------

    def handle_message(self, user_id: str, text: str) -> str:
        """统一消息入口，自动识别意图并分发处理。

        处理流程：
        1. 输入校验
        2. 调用 recognize_intent 识别意图
        3. 根据意图分发到对应 _handle_* 方法
        4. 返回格式化文本结果

        Args:
            user_id: 用户 ID。
            text: 用户输入的原始文本。

        Returns:
            处理结果的文本回复。
        """
        if not text or not text.strip():
            return "请输入内容，发送 /help 查看可用命令。"

        intent, args = recognize_intent(text)

        handler_map: dict[Intent, Any] = {
            Intent.SEARCH: self._handle_search,
            Intent.TODAY: self._handle_today,
            Intent.TOP: self._handle_top,
            Intent.SUBSCRIBE: self._handle_subscribe,
            Intent.HELP: self._handle_help,
            Intent.UNKNOWN: self._handle_unknown,
        }

        handler = handler_map.get(intent, self._handle_unknown)
        return handler(user_id, args)

    # ------------------------------------------------------------------
    # 权限检查快捷方法
    # ------------------------------------------------------------------

    def _require_permission(self, user_id: str, permission: Permission) -> str | None:
        """检查权限，返回错误消息或 None。

        Args:
            user_id: 用户 ID。
            permission: 所需权限。

        Returns:
            权限不足时返回错误消息字符串，满足时返回 None。
        """
        if not self.permission_manager.check(user_id, permission):
            return (
                f"⛔ 权限不足：当前操作需要 {permission.value.upper()} 权限。"
                f" 你当前的权限级别为 {self.permission_manager.get_permission(user_id).value.upper()}。"
            )
        return None

    # ------------------------------------------------------------------
    # 消息处理器
    # ------------------------------------------------------------------

    def _handle_search(self, user_id: str, args: str) -> str:
        """处理搜索请求 — 需 READ 权限。

        Args:
            user_id: 用户 ID。
            args: 搜索参数字符串。

        Returns:
            搜索结果或错误提示。
        """
        perm_err = self._require_permission(user_id, Permission.READ)
        if perm_err:
            return perm_err

        parsed = parse_search_args(args)
        results = self.search_engine.search(
            keyword=parsed["keyword"],
            tags=parsed["tags"],
            date_from=parsed["date_from"],
            date_to=parsed["date_to"],
            category=parsed["category"],
        )
        return format_search_results(results, keyword=parsed["keyword"])

    def _handle_today(self, user_id: str, _args: str) -> str:
        """处理今日文章请求 — 需 READ 权限。

        Args:
            user_id: 用户 ID。
            _args: 未使用。

        Returns:
            今日文章列表或提示。
        """
        perm_err = self._require_permission(user_id, Permission.READ)
        if perm_err:
            return perm_err

        today_str = date.today().isoformat()
        results = self.search_engine.get_today_articles(limit=20)
        if not results:
            return f"今日（{today_str}）暂无采集文章。"
        return format_search_results(results, title=f"今日文章（{today_str}）")

    def _handle_top(self, user_id: str, args: str) -> str:
        """处理热门排行请求 — 需 READ 权限。

        Args:
            user_id: 用户 ID。
            args: 可选的数量参数。

        Returns:
            Top N 文章列表或提示。
        """
        perm_err = self._require_permission(user_id, Permission.READ)
        if perm_err:
            return perm_err

        try:
            limit = int(args) if args.strip() else 10
        except ValueError:
            limit = 10
        limit = min(max(limit, 1), 20)

        results = self.search_engine.get_top_articles(limit=limit)
        if not results:
            return "知识库为空，暂无文章。"
        return format_search_results(results, title=f"评分 Top {limit}")

    def _handle_subscribe(self, user_id: str, args: str) -> str:
        """处理订阅管理请求 — 需 WRITE 权限。

        支持子命令：
            (无参数) / list / 列表 → 查看当前订阅
            add / 添加 / 订阅 <标签>  → 添加订阅
            remove / del / 取消 / 退订 <标签> → 移除订阅
            直接输入标签名 → 添加订阅

        Args:
            user_id: 用户 ID。
            args: 子命令和标签参数。

        Returns:
            订阅操作结果文本。
        """
        perm_err = self._require_permission(user_id, Permission.WRITE)
        if perm_err:
            return perm_err

        subs = self.subscription_manager

        # 查询当前订阅
        if not args or args in ("list", "列表", "查看"):
            current = subs.get_user_subscriptions(user_id)
            if not current:
                return (
                    "你还没有订阅任何标签。\n"
                    "使用 `/subscribe add <标签>` 来添加订阅。"
                )
            return f"你的订阅标签：{', '.join(current)}"

        # 解析操作类型
        parts = args.split(maxsplit=1)
        action = parts[0] if parts else ""
        tag = parts[1].strip().strip(",.!?，。！？") if len(parts) > 1 else ""

        # 移除操作
        if action in ("remove", "del", "取消", "取消订阅", "退订", "删除"):
            if not tag:
                return "请指定要移除的标签，例如：`/subscribe remove agent`"
            current = subs.get_user_subscriptions(user_id)
            if tag not in current:
                hint = f"（当前订阅：{', '.join(current)}）" if current else "（当前无订阅）"
                return f"你未订阅标签 [{tag}]。{hint}"
            subs.remove_subscription(user_id, tag)
            return f"已取消订阅标签：[{tag}]"

        # 添加操作（显式 add 或默认行为）
        if action in ("add", "添加", "订阅"):
            real_tag = tag
        else:
            # 将整段 args 视为标签名
            real_tag = args.strip().strip(",.!?，。！？")

        if not real_tag:
            return "请指定要订阅的标签，例如：`/subscribe add agent`"

        subs.add_subscription(user_id, real_tag)
        return f"已订阅标签：[{real_tag}]"

    def _handle_help(self, _user_id: str, _args: str) -> str:
        """处理帮助请求。

        Args:
            _user_id: 用户 ID（未使用）。
            _args: 未使用。

        Returns:
            帮助信息文本。
        """
        return _HELP_TEXT

    def _handle_unknown(self, _user_id: str, args: str) -> str:
        """处理未识别的意图。

        Args:
            _user_id: 用户 ID（未使用）。
            args: 原始输入文本。

        Returns:
            提示信息和可用命令列表。
        """
        return (
            f"无法识别：「{args}」\n\n"
            "支持的操作：搜索(/search)、今日文章(/today)、"
            "热门排行(/top)、订阅管理(/subscribe)\n"
            "发送 /help 查看完整帮助。"
        )
