"""
RSS 采集条数两层配置的本地验证测试（无网络、不调用 LLM）

覆盖:
  - resolve_feed_limit: 源级 limit 优先 / 未配置回退全局 / 非法配置回退
  - load_rss_sources: yaml 中 limit 的解析与非法值容错
  - collect_rss_sources: 逐源按两层配置抓取（monkeypatch fetch_feed，不发真实请求）
"""

import pytest

import workflows.rss_collector as rc


# ============================================================
# resolve_feed_limit — 两层配置的解析规则
# ============================================================

def test_source_limit_takes_precedence_over_global():
    assert rc.resolve_feed_limit({"limit": 3}, 10) == 3
    # 源级 limit 比全局小，同样生效
    assert rc.resolve_feed_limit({"limit": 1}, 10) == 1


def test_falls_back_to_global_when_unset():
    assert rc.resolve_feed_limit({}, 10) == 10
    assert rc.resolve_feed_limit({"limit": None}, 10) == 10


@pytest.mark.parametrize("bad", [0, -3, "5", 2.5, True, []])
def test_invalid_source_limit_falls_back_to_global(bad):
    assert rc.resolve_feed_limit({"limit": bad}, 10) == 10


# ============================================================
# load_rss_sources — yaml 解析
# ============================================================

_YAML = """
sources:
  - name: "A"
    url: "https://a.example/rss"
    category: "综合技术"
    enabled: true
    limit: 3
  - name: "B"
    url: "https://b.example/rss"
    category: "AI研究"
    enabled: true
  - name: "C"
    url: "https://c.example/rss"
    category: "公司博客"
    enabled: true
    limit: 0
  - name: "D-禁用"
    url: "https://d.example/rss"
    category: "框架"
    enabled: false
"""


@pytest.fixture()
def config_file(tmp_path):
    path = tmp_path / "rss_sources.yaml"
    path.write_text(_YAML, encoding="utf-8")
    return path


def test_load_reads_source_level_limit(config_file):
    feeds = rc.load_rss_sources(config_file)
    by_name = {f["name"]: f for f in feeds}
    assert by_name["A"]["limit"] == 3
    # 未配置 limit 的源不携带该字段，交给 resolve_feed_limit 回退全局
    assert "limit" not in by_name["B"]
    # 禁用源不参与采集
    assert "D-禁用" not in by_name


def test_load_drops_invalid_limit(config_file):
    feeds = rc.load_rss_sources(config_file)
    by_name = {f["name"]: f for f in feeds}
    # limit: 0 非法 → 丢弃该字段，回退全局配置
    assert "limit" not in by_name["C"]


# ============================================================
# collect_rss_sources — 逐源生效
# ============================================================

def test_collect_applies_two_layer_limits(monkeypatch):
    monkeypatch.setenv("RSS_ENABLED", "1")
    seen: list[tuple[str, int]] = []
    fake = [
        {"title": f"A-{i}", "url": f"https://a.example/{i}", "description": ""}
        for i in range(20)
    ]

    def fake_fetch(feed, per_feed_limit):
        seen.append((feed["name"], per_feed_limit))
        return fake[:per_feed_limit], 0

    monkeypatch.setattr(rc, "fetch_feed", fake_fetch)
    monkeypatch.setattr(
        rc, "load_rss_sources",
        lambda: [
            {"name": "A", "url": "https://a.example/rss", "category": "综合技术", "limit": 3},
            {"name": "B", "url": "https://b.example/rss", "category": "AI研究"},
        ],
    )

    sources, errs = rc.collect_rss_sources(per_source_limit=10)

    assert errs == 0
    # 源级 limit=3 生效；未配置 limit 的源回退全局 10
    assert seen == [("A", 3), ("B", 10)]
    assert len(sources) == 13
    assert sum(1 for s in sources if s["source"] == "A") == 3
    assert sum(1 for s in sources if s["source"] == "B") == 10