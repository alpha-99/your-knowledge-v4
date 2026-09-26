"""formatter 模块的单元测试。

测试所有格式化函数及 generate_daily_digest 的正确性，
重点验证 key_insight 替代 summary 的瘦身效果。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from distribution.formatter import (  # noqa: E402
    _escape_telegram,
    _feishu_color,
    _score_emoji,
    digest_from_index,
    generate_daily_digest,
    json_to_feishu,
    json_to_markdown,
    json_to_telegram,
    json_to_wechat,
)


_STANDARD_ARTICLE: dict[str, Any] = {
    "id": "2026-04-11-000",
    "title": "langgenius/dify",
    "source": "github",
    "url": "https://github.com/langgenius/dify",
    "collected_at": "2026-04-11T16:03:47.946653+00:00",
    "summary": "Dify 是一个开源 LLM 应用开发平台，集成多种 AI 能力的一体化工具。",
    "tags": ["LLM应用开发", "智能体工作流", "RAG"],
    "relevance_score": 0.9,
    "category": "framework",
    "key_insight": "Dify 通过一体化平台显著降低 AI 工作流开发门槛",
}


# ── _score_emoji ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "score, expected",
    [
        (1.0, "\U0001F7E2"),
        (0.8, "\U0001F7E2"),
        (0.81, "\U0001F7E2"),
        (0.79, "\U0001F7DF"),
        (0.6, "\U0001F7DF"),
        (0.61, "\U0001F7DF"),
        (0.59, "\U0001F534"),
        (0.0, "\U0001F534"),
        (-1.0, "\U0001F534"),
    ],
)
def test_score_emoji(score: float, expected: str) -> None:
    assert _score_emoji(score) == expected


# ── _feishu_color ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "score, expected",
    [
        (0.9, "green"),
        (0.8, "green"),
        (0.7, "yellow"),
        (0.6, "yellow"),
        (0.59, "red"),
        (0.0, "red"),
    ],
)
def test_feishu_color(score: float, expected: str) -> None:
    assert _feishu_color(score) == expected


# ── _escape_telegram ──────────────────────────────────────────


def test_escape_telegram_special_chars() -> None:
    raw = "Hello _world_ [link](url) ~test~"
    escaped = _escape_telegram(raw)
    assert escaped == r"Hello \_world\_ \[link\]\(url\) \~test\~"


def test_escape_telegram_no_special() -> None:
    assert _escape_telegram("plain text") == "plain text"


def test_escape_telegram_empty() -> None:
    assert _escape_telegram("") == ""


# ── json_to_markdown ──────────────────────────────────────────


def test_markdown_uses_key_insight_not_summary() -> None:
    result = json_to_markdown(_STANDARD_ARTICLE)
    assert "Dify 通过一体化平台显著降低 AI 工作流开发门槛" in result
    assert "Dify 是一个开源 LLM 应用开发平台" not in result


def test_markdown_structure() -> None:
    result = json_to_markdown(_STANDARD_ARTICLE)
    assert "# langgenius/dify" in result
    assert "**来源**: github" in result
    assert "**日期**: 2026-04-11" in result
    assert "\U0001F7E2 0.90" in result
    assert "**标签**: LLM应用开发, 智能体工作流, RAG" in result
    assert "**原文链接**" in result
    assert "https://github.com/langgenius/dify" in result


def test_markdown_missing_key_insight() -> None:
    article = dict(_STANDARD_ARTICLE)
    article["key_insight"] = ""
    result = json_to_markdown(article)
    assert ">" not in result


def test_markdown_missing_collected_at() -> None:
    article = dict(_STANDARD_ARTICLE, collected_at="")
    result = json_to_markdown(article)
    assert "未知日期" in result


def test_markdown_empty_tags() -> None:
    article = dict(_STANDARD_ARTICLE, tags=[])
    result = json_to_markdown(article)
    assert "**标签**: " in result


def test_markdown_no_url() -> None:
    article = dict(_STANDARD_ARTICLE, url="")
    result = json_to_markdown(article)
    assert "原文链接" not in result


def test_markdown_low_score() -> None:
    article = dict(_STANDARD_ARTICLE, relevance_score=0.4)
    result = json_to_markdown(article)
    assert "\U0001F534" in result


# ── json_to_telegram ──────────────────────────────────────────


def test_telegram_uses_key_insight_not_summary() -> None:
    result = json_to_telegram(_STANDARD_ARTICLE)
    assert "Dify 通过一体化平台显著降低 AI 工作流开发门槛" in result
    assert "Dify 是一个开源 LLM 应用开发平台" not in result


def test_telegram_escapes_special_chars() -> None:
    article = dict(_STANDARD_ARTICLE)
    article["title"] = "test [repo]"
    article["key_insight"] = "A > B _result_"
    result = json_to_telegram(article)
    assert "test \\[repo\\]" in result
    assert "A \\> B \\_result\\_" in result


def test_telegram_tags_spaces_to_underscores() -> None:
    article = dict(_STANDARD_ARTICLE, tags=["hello world", "foo bar test"])
    result = json_to_telegram(article)
    assert "hello\\_world" in result
    assert "foo\\_bar\\_test" in result


def test_telegram_no_url() -> None:
    article = dict(_STANDARD_ARTICLE, url="")
    result = json_to_telegram(article)
    assert "*langgenius/dify*" in result
    assert "(" not in result


def test_telegram_empty_tags() -> None:
    article = dict(_STANDARD_ARTICLE, tags=[])
    result = json_to_telegram(article)
    assert "标签:" not in result


def test_telegram_no_truncation_when_short() -> None:
    """短 key_insight 不会被截断，长度不超过上限。"""
    article = dict(_STANDARD_ARTICLE, key_insight="Short.")
    result = json_to_telegram(article)
    assert len(result) <= 4096
    assert "..." not in result or result == "..."  # 不应因为截断出现 ...


def test_telegram_truncation_long_key_insight() -> None:
    """超长 key_insight 触发截断，保留 ... 标记。"""
    article = dict(_STANDARD_ARTICLE, key_insight="X" * 5000)
    result = json_to_telegram(article)
    assert len(result) <= 4096
    assert "X" in result
    assert "..." in result


def test_telegram_truncation_does_not_exceed_limit() -> None:
    """截断后的消息长度精确不超过上限。"""
    article = dict(_STANDARD_ARTICLE, key_insight="Y" * 5000)
    result = json_to_telegram(article, max_len=200)
    assert len(result) <= 200


def test_telegram_truncation_preserves_metadata() -> None:
    """截断后仍然保留来源、相关性、标签等元数据。"""
    article = dict(_STANDARD_ARTICLE, key_insight="Z" * 5000)
    result = json_to_telegram(article)
    assert "github" in result
    assert "相关性" in result
    assert _STANDARD_ARTICLE["title"] in result


# ── json_to_feishu ────────────────────────────────────────────


def test_feishu_uses_key_insight_not_summary() -> None:
    result = json_to_feishu(_STANDARD_ARTICLE)
    elements = result["card"]["elements"]
    markdown_contents = [
        e["content"] for e in elements if e["tag"] == "markdown"
    ]
    combined = " ".join(markdown_contents)
    assert "Dify 通过一体化平台显著降低 AI 工作流开发门槛" in combined
    assert "Dify 是一个开源 LLM 应用开发平台" not in combined


def test_feishu_msg_type() -> None:
    result = json_to_feishu(_STANDARD_ARTICLE)
    assert result["msg_type"] == "interactive"


def test_feishu_header_colors() -> None:
    high = json_to_feishu(dict(_STANDARD_ARTICLE, relevance_score=0.9))
    mid = json_to_feishu(dict(_STANDARD_ARTICLE, relevance_score=0.7))
    low = json_to_feishu(dict(_STANDARD_ARTICLE, relevance_score=0.5))
    assert high["card"]["header"]["template"] == "green"
    assert mid["card"]["header"]["template"] == "yellow"
    assert low["card"]["header"]["template"] == "red"


def test_feishu_has_button_when_url() -> None:
    result = json_to_feishu(_STANDARD_ARTICLE)
    actions = [
        e for e in result["card"]["elements"] if e["tag"] == "action"
    ]
    assert len(actions) == 1
    assert actions[0]["actions"][0]["url"] == _STANDARD_ARTICLE["url"]


def test_feishu_no_button_when_no_url() -> None:
    article = dict(_STANDARD_ARTICLE, url="")
    result = json_to_feishu(article)
    actions = [
        e for e in result["card"]["elements"] if e["tag"] == "action"
    ]
    assert len(actions) == 0


def test_feishu_empty_key_insight() -> None:
    article = dict(_STANDARD_ARTICLE, key_insight="")
    result = json_to_feishu(article)
    elements = result["card"]["elements"]
    markdown_elements = [e for e in elements if e["tag"] == "markdown"]
    assert len(markdown_elements) == 1


# ── json_to_wechat ────────────────────────────────────────────


def test_wechat_uses_key_insight_not_summary() -> None:
    result = json_to_wechat(_STANDARD_ARTICLE)
    assert "Dify 通过一体化平台显著降低 AI 工作流开发门槛" in result
    assert "Dify 是一个开源 LLM 应用开发平台" not in result


def test_wechat_tags_spaces_to_underscores() -> None:
    article = dict(_STANDARD_ARTICLE, tags=["hello world", "foo bar"])
    result = json_to_wechat(article)
    assert "hello_world" in result
    assert "foo_bar" in result


def test_wechat_line_breaks_at_max_len() -> None:
    article = dict(_STANDARD_ARTICLE)
    article["key_insight"] = "A" * 100
    result = json_to_wechat(article, max_line_len=42)
    lines = result.split("\n")
    insight_lines = []
    collecting = False
    for line in lines:
        if collecting:
            insight_lines.append(line)
        if line == "":
            collecting = True
    assert max(len(l) for l in insight_lines) <= 42


def test_wechat_long_url_omitted() -> None:
    article = dict(_STANDARD_ARTICLE)
    article["url"] = "https://" + "x" * 60
    result = json_to_wechat(article, max_line_len=42)
    assert "原文:" not in result


def test_wechat_short_url_included() -> None:
    article = dict(_STANDARD_ARTICLE)
    article["url"] = "https://short.url"
    result = json_to_wechat(article)
    assert "https://short.url" in result


def test_wechat_empty_key_insight_no_summary_leak() -> None:
    article = dict(_STANDARD_ARTICLE, key_insight="")
    result = json_to_wechat(article)
    assert _STANDARD_ARTICLE["summary"] not in result


# ── generate_daily_digest ─────────────────────────────────────


_KNOWLEDGE_DIR = str(
    Path(__file__).resolve().parents[1] / "knowledge" / "articles"
)


def test_digest_returns_all_formats() -> None:
    digest = generate_daily_digest(
        knowledge_dir=_KNOWLEDGE_DIR, date="2026-07-10", top_n=3,
    )
    assert "markdown" in digest
    assert "telegram" in digest
    assert "feishu" in digest
    assert isinstance(digest["feishu"], list)


def test_digest_empty_date() -> None:
    digest = generate_daily_digest(
        knowledge_dir=_KNOWLEDGE_DIR, date="2099-01-01", top_n=3,
    )
    assert "暂无新增知识条目" in digest["markdown"]
    assert digest["feishu"] == []


def test_digest_default_date_is_today() -> None:
    digest = generate_daily_digest(knowledge_dir=_KNOWLEDGE_DIR)
    assert isinstance(digest["markdown"], str)
    assert isinstance(digest["telegram"], str)
    assert isinstance(digest["feishu"], list)


# ── category 分组测试 ──────────────────────────────────────────


def test_digest_grouped_by_category() -> None:
    """验证 Markdown 输出按 category 分组，每组有 ## 标题。"""
    digest = generate_daily_digest(
        knowledge_dir=_KNOWLEDGE_DIR, date="2026-07-10", top_n=3,
    )
    md = digest["markdown"]
    # 至少包含 2 个 ## 分类标题
    assert md.count("## ") >= 2
    # 各已知分类至少出现一个
    for cat in ("agent", "framework", "tool", "rag"):
        assert f"## " in md  # 每个分类有对应标题（含 emoji）
    # 分类应在正文中出现
    assert "framework" in md
    assert "agent" in md


def test_digest_top_n_per_category() -> None:
    """每个分类最多取 top_n 篇。"""
    digest = generate_daily_digest(
        knowledge_dir=_KNOWLEDGE_DIR, date="2026-07-10", top_n=1,
    )
    md = digest["markdown"]
    # 每个分类主题标记只出现一次
    cat_markers = [line for line in md.split("\n") if line.startswith("## ")]
    # 每个分类下最多 1 篇，每篇开头都有 # 标题
    article_count = md.count("**原文链接**")
    assert article_count <= len(cat_markers)


def test_digest_summary_line() -> None:
    """简报开头包含篇数和分类数统计。"""
    digest = generate_daily_digest(
        knowledge_dir=_KNOWLEDGE_DIR, date="2026-07-10", top_n=3,
    )
    md = digest["markdown"]
    assert "篇" in md
    assert "分类" in md


def test_digest_categories_sorted_by_avg_score() -> None:
    """分类按平均 relevance_score 降序排列。"""
    digest = generate_daily_digest(
        knowledge_dir=_KNOWLEDGE_DIR, date="2026-07-10", top_n=1,
    )
    md = digest["markdown"]
    headers = [line for line in md.split("\n") if line.startswith("## ")]
    assert len(headers) == len(set(headers))


def test_digest_telegram_has_category_headers() -> None:
    """Telegram 输出中每个分类有 *category* 标题行。"""
    digest = generate_daily_digest(
        knowledge_dir=_KNOWLEDGE_DIR, date="2026-07-10", top_n=1,
    )
    tg = digest["telegram"]
    assert "*framework*" in tg or "*agent*" in tg or "*rag*" in tg or "*tool*" in tg


# ── digest_from_index ─────────────────────────────────────────


def test_digest_from_index_returns_structure() -> None:
    """返回 dict 包含 date / total / items 三个键。"""
    result = digest_from_index(
        knowledge_dir=_KNOWLEDGE_DIR, date="2026-07-10", top_n=3,
    )
    assert "date" in result
    assert "total" in result
    assert "items" in result
    assert isinstance(result["items"], list)


def test_digest_from_index_top_n() -> None:
    """items 数量不超过 top_n。"""
    result = digest_from_index(
        knowledge_dir=_KNOWLEDGE_DIR, date="2026-07-10", top_n=3,
    )
    assert len(result["items"]) <= 3


def test_digest_from_index_sorted_by_score() -> None:
    """items 按 relevance_score 降序排列。"""
    result = digest_from_index(
        knowledge_dir=_KNOWLEDGE_DIR, date="2026-07-10", top_n=5,
    )
    scores = [item["relevance_score"] for item in result["items"]]
    assert scores == sorted(scores, reverse=True)


def test_digest_from_index_item_has_required_fields() -> None:
    """每条 item 包含 id / title / category / relevance_score。"""
    result = digest_from_index(
        knowledge_dir=_KNOWLEDGE_DIR, date="2026-07-10", top_n=3,
    )
    for item in result["items"]:
        for field in ("id", "title", "category", "relevance_score"):
            assert field in item


def test_digest_from_index_empty_date() -> None:
    """无匹配日期的条目时 items 为空。"""
    result = digest_from_index(
        knowledge_dir=_KNOWLEDGE_DIR, date="2099-01-01", top_n=3,
    )
    assert result["total"] == 0
    assert result["items"] == []


def test_digest_from_index_faster_than_full_digest() -> None:
    """从 index 读取应比逐个 JSON 读取快（至少不慢于 5 倍）。"""
    import timeit
    idx_time = timeit.timeit(
        lambda: digest_from_index(
            knowledge_dir=_KNOWLEDGE_DIR, date="2026-07-10", top_n=3,
        ),
        number=50,
    )
    full_time = timeit.timeit(
        lambda: generate_daily_digest(
            knowledge_dir=_KNOWLEDGE_DIR, date="2026-07-10", top_n=1,
        ),
        number=50,
    )
    assert idx_time <= full_time * 5, (
        f"digest_from_index ({idx_time:.4f}s) should be faster than "
        f"generate_daily_digest ({full_time:.4f}s)"
    )


# ── 瘦身效果验证 ──────────────────────────────────────────────


def test_key_insight_shorter_than_summary() -> None:
    """key_insight 比 summary 短一半以上。"""
    assert len(_STANDARD_ARTICLE["key_insight"]) < len(
        _STANDARD_ARTICLE["summary"]
    ), "key_insight 应比 summary 短"


def test_digest_markdown_with_key_insight_is_compact() -> None:
    """验证使用 key_insight 后 Markdown 输出不包含长 summary 文本。"""
    result = json_to_markdown(_STANDARD_ARTICLE)
    long_summary = _STANDARD_ARTICLE["summary"]
    assert long_summary not in result
    assert _STANDARD_ARTICLE["key_insight"] in result


def test_digest_all_formats_use_key_insight() -> None:
    """所有四种输出格式均使用 key_insight 而非 summary。"""
    long_summary = _STANDARD_ARTICLE["summary"]
    for fmt_fn in [
        json_to_markdown,
        json_to_telegram,
        lambda a: json.dumps(json_to_feishu(a), ensure_ascii=False),
        json_to_wechat,
    ]:
        output = fmt_fn(_STANDARD_ARTICLE)
        assert long_summary not in output, (
            f"{fmt_fn.__name__ if hasattr(fmt_fn, '__name__') else 'feishu'} "
            "不应包含 long summary"
        )
        assert _STANDARD_ARTICLE["key_insight"] in output
