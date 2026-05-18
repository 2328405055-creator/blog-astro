# textscripts · generators/daily_generator.py — 文章生成

import os
import re
import urllib.parse
import logging

from textscripts.config import POSTS_DIR, JSON_PATH
from textscripts.utils.file_ops import load_json, save_json, slugify, str_hash, today_str
from textscripts.utils.llm import translate_title
from textscripts.scrapers.news_scraper import fetch_all_feeds, build_search_link, fetch_fill
from textscripts.scrapers.firecrawl_scraper import enrich_batch

logger = logging.getLogger(__name__)

# ============================================================
# 分类逻辑
# ============================================================

CAT_NAMES_CB = {
    "selection": "选品技巧", "ozon": "Ozon运营", "yandex": "Yandex运营",
    "russia-market": "俄罗斯市场", "logistics": "物流收款", "tools": "工具教程",
}
CAT_NAMES_FIT = {
    "male": "男性训练", "female": "女性训练", "yoga-mat": "瑜伽垫动作",
    "plan": "每日计划", "diet": "饮食建议",
}
AI_CAT_NAMES = {
    "ai-tools": "AI工具", "ai-industry": "行业动态",
    "ai-ecommerce": "AI与电商", "ai-tutorial": "AI教程",
}


def classify_cross_border(title):
    t = title.lower()
    if any(w in t for w in ["选品", "热销", "蓝海", "爆款", "品类", "趋势报告"]):
        return "selection"
    if any(w in t for w in ["yandex", "yandex market"]):
        return "yandex"
    if any(w in t for w in ["物流", "仓储", "fbo", "fbs", "发货", "头程", "海外仓"]):
        return "logistics"
    if any(w in t for w in ["收款", "回款", "卢布", "支付", "汇率"]):
        return "logistics"
    if any(w in t for w in ["政策", "法规", "关税", "认证", "合规", "eac"]):
        return "tools"
    if any(w in t for w in ["工具", "软件", "erp", "翻译", "数据"]):
        return "tools"
    if any(w in t for w in ["市场", "俄罗斯", "经济", "消费", "趋势"]):
        return "russia-market"
    if any(w in t for w in ["ozon", "ozon", "оzon"]):
        return "ozon"
    return "selection"


def classify_fitness(title):
    t = title.lower()
    if any(w in t for w in ["男性", "男人", "男生", "male", "men", "man"]):
        return "male"
    if any(w in t for w in ["女性", "女人", "女生", "female", "women", "woman"]):
        return "female"
    if any(w in t for w in ["瑜伽垫", "yoga mat", "yoga"]):
        return "yoga-mat"
    if any(w in t for w in ["饮食", "营养", "吃", "食物", "蛋白质", "减脂", "diet", "nutrition"]):
        return "diet"
    if any(w in t for w in ["计划", "安排", "每周", "每日", "routine", "plan", "schedule", "program"]):
        return "plan"
    return "yoga-mat"


def classify_ai(title):
    t = title.lower()
    if any(w in t for w in ["工具", "tool", "应用", "platform"]):
        return "ai-tools"
    if any(w in t for w in ["电商", "跨境", "ecommerce", "零售", "卖家"]):
        return "ai-ecommerce"
    if any(w in t for w in ["教程", "指南", "tutorial", "guide", "how"]):
        return "ai-tutorial"
    return "ai-industry"


# ============================================================
# Markdown 构建
# ============================================================

def build_cross_border_post(entry):
    title = entry["title"]
    source_name = entry["source_name"]
    domain = entry["domain"]
    link = entry["link"]
    cat = classify_cross_border(title)
    cat_name = CAT_NAMES_CB.get(cat, "跨境电商")
    search_url = build_search_link(title, domain)
    enriched = entry.get("enriched")
    date_str = today_str()

    body = ""
    if enriched and enriched.get("content"):
        body = enriched["content"]
        kp = enriched.get("key_points", [])
        if kp:
            body += "\n\n## 核心要点\n\n" + "\n".join(f"- {p}" for p in kp)
    else:
        body = """## 学习要点

阅读这篇教程后，你将会学到：

1. **实操方法:** 具体的操作步骤和落地技巧
2. **避坑指南:** 新手常见错误及如何避免
3. **进阶思路:** 从入门到精通的学习路径
"""

    return f"""# {title}

> 📂 分类: {cat_name}
> 📅 采集日期: {date_str}
> 📰 来源: **{source_name}**（{domain}）

---

{body}

---

## 查看原文

📎 **原文链接:** [点击查看原文]({link})
🔍 **站内搜索:** [在 {source_name} 站内搜索本文]({search_url})

> 📚 本文内容来自 **{source_name}**，版权归原来源所有。
""", cat


def build_fitness_post(entry):
    title = entry["title"]
    source_name = entry["source_name"]
    domain = entry["domain"]
    link = entry["link"]
    cat = classify_fitness(title)
    cat_name = CAT_NAMES_FIT.get(cat, "健身")
    search_url = build_search_link(title, domain)
    enriched = entry.get("enriched")
    yt_query = urllib.parse.quote(title[:50])
    yt_link = f"https://www.youtube.com/results?search_query={yt_query}"
    date_str = today_str()

    sources_info = entry.get("_sources", [])
    body = ""
    if enriched and enriched.get("content"):
        body = enriched["content"]
        if sources_info:
            body += "\n\n## 参考来源\n\n" + "\n".join(f"- {s}" for s in sources_info)
    else:
        body = """## 训练建议

无论文章中提到哪种训练方法，请牢记:

- 🔹 **动作标准优先:** 宁可少做几个，也不牺牲动作质量
- 🔹 **循序渐进:** 每周比上周多做1-2个就是进步
- 🔹 **充分休息:** 肌肉在休息时生长，每周至少休息1天
- 🔹 **配合饮食:** 徒手训练配合合理饮食才能看到线条变化
- 🔹 **只需瑜伽垫:** 本文推荐的所有训练只需一张瑜伽垫即可
"""

    return f"""# {title}

> 💪 分类: {cat_name}
> 📅 采集日期: {date_str}
> 📰 来源: **{source_name}**

---

{body}

---

## 查看原文与视频教程

📎 **原文链接:** [点击查看原文]({link})
🔍 **搜索原文:** [在 {source_name} 站内搜索]({search_url})
🎬 **YouTube 视频教程:** [搜索相关训练视频]({yt_link})

> ⚠️ 训练前请评估自身状况，量力而行。
""", cat


def build_ai_post(entry):
    title = entry["title"]
    source_name = entry["source_name"]
    domain = entry["domain"]
    link = entry["link"]
    cat = classify_ai(title)
    cat_name = AI_CAT_NAMES.get(cat, "AI新闻")
    search_url = build_search_link(title, domain)
    enriched = entry.get("enriched")
    date_str = today_str()

    sources_info = entry.get("_sources", [])
    body = ""
    if enriched and enriched.get("content"):
        body = enriched["content"]
        if sources_info:
            body += "\n\n## 参考来源\n\n" + "\n".join(f"- {s}" for s in sources_info)
    else:
        body = """## AI 与跨境电商的交汇

无论这则 AI 新闻的具体内容是什么，对跨境电商卖家来说，AI 正在改变:

- 🔹 **选品智能化:** AI 工具正在帮助卖家分析市场趋势和消费者偏好
- 🔹 **内容生成:** 产品描述、广告文案的 AI 自动化处理
- 🔹 **客服优化:** AI 翻译和智能客服降低跨境沟通成本
- 🔹 **数据驱动:** 从经验决策转向 AI 辅助的数据决策
"""

    return f"""# {title}

> 🤖 分类: {cat_name}
> 📅 采集日期: {date_str}
> 📰 来源: **{source_name}**

---

{body}

---

## 查看原文

📎 **原文链接:** [点击查看原文]({link})
🔍 **站内搜索:** [在 {source_name} 站内搜索]({search_url})

> 📚 本文内容来自 **{source_name}**，版权归原来源所有。
""", cat


def clean_title(title: str) -> str:
    """清理标题：去来源后缀、限制长度、去多余空格"""
    # 去掉来源后缀 (如 " - BBC News", " | 36kr", " - 亿邦动力网")
    title = re.sub(r'\s*[-|—–]\s*(BBC|CNN|36kr|雨果|亿邦|野莓|Ozon|WB).*$', '', title, flags=re.I)
    title = re.sub(r'\s*[-|—–]\s*\S*(?:com|cn|ru|news|blog)\S*$', '', title, flags=re.I)
    # 去掉末尾多余的分隔
    title = re.sub(r'\s*[-|—–]\s*$', '', title)
    # 限制长度
    if len(title) > 60:
        title = title[:57] + '...'
    return title.strip()


def quality_pass(entry, md_content: str, section: str) -> tuple[bool, str]:
    """快速质量检查 (发布前)"""
    title = entry.get("title", "")
    link = entry.get("link", "")
    enriched = entry.get("enriched")
    word_count = len(md_content)

    # 标题不可空或过短
    if len(title) < 10:
        return False, f"标题过短 ({len(title)}字)"

    # 标题不可过长
    if len(title) > 80:
        return False, f"标题过长 ({len(title)}字)"

    # 必须有来源链接
    if not link:
        return False, "无来源链接"

    # 字数至少 300
    if word_count < 300:
        return False, f"字数不足 ({word_count})"

    # 过滤纯广告/垃圾标题
    spam_kw = ["免费领取", "限时优惠", "点击下载", "加微信", "扫码", "关注公众号"]
    if any(kw in title for kw in spam_kw):
        return False, f"垃圾标题: {title[:40]}"

    # 必须有富化内容，不能是空壳
    if not enriched or not enriched.get("content"):
        return False, "无富化内容 (RSS 抓取失败)"

    return True, ""


# ============================================================
# 文章生成流水线
# ============================================================

def build_and_save(entry, section, date_str, existing_slugs):
    title = entry["title"]
    title = translate_title(title)
    title = clean_title(title)
    if title != entry["title"]:
        logger.info(f"翻译+清理: {entry['title'][:30]}... -> {title[:30]}...")
    entry["title"] = title

    if section == "cross-border":
        md_content, cat = build_cross_border_post(entry)
    elif section == "fitness":
        md_content, cat = build_fitness_post(entry)
    else:
        md_content, cat = build_ai_post(entry)

    ok, reason = quality_pass(entry, md_content, section)
    if not ok:
        logger.warning(f"质量过滤: {title[:40]}... — {reason}")
        return None

    slug_base = slugify(title) + "-" + date_str
    slug = slug_base
    i = 1
    while slug in existing_slugs:
        slug = slug_base + "-" + str(i)
        i += 1
    existing_slugs.add(slug)

    md_path = os.path.join(POSTS_DIR, slug + ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    excerpt = title[:150]
    enriched = entry.get("enriched") or {}
    all_posts = load_json(JSON_PATH)
    all_posts.insert(0, {
        "slug": slug,
        "title": title,
        "date": date_str,
        "lastmod": date_str,
        "excerpt": excerpt,
        "cat": section,
        "sub": cat,
        "source": entry["link"],
        "source_name": f"{entry['source_name']} ({entry['domain']})",
        "has_content": bool(enriched and enriched.get("content")),
        "word_count": enriched.get("word_count", 0),
    })
    save_json(JSON_PATH, all_posts)

    label = "CB" if section == "cross-border" else ("Fit" if section == "fitness" else "AI")
    logger.info(f"[{label}/{cat}] {title[:50]}... <- {entry['source_name']}")

    return {"title": title, "cat": section}


def generate_posts(limit_cb=4, limit_fit=3, limit_ai=3):
    all_posts = load_json(JSON_PATH)
    existing_slugs = set(p["slug"] for p in all_posts)
    posted_titles = set()
    for p in all_posts:
        if "source_name" in p:
            posted_titles.add(str_hash(p["title"]))

    new_posts = []
    date_str = today_str()

    # 跨境电商
    logger.info("抓取跨境电商新闻...")
    cb_entries = fetch_all_feeds("cross-border", limit_per_feed=6)
    cb_fresh = [e for e in cb_entries if str_hash(e["title"]) not in posted_titles][:limit_cb]
    logger.info(f"获取 {len(cb_entries)} 条，{len(cb_fresh)} 条可用")

    # 健身
    logger.info("抓取健身内容...")
    fit_entries = fetch_all_feeds("fitness", limit_per_feed=4)
    fit_fresh = [e for e in fit_entries if str_hash(e["title"]) not in posted_titles][:limit_fit]
    logger.info(f"获取 {len(fit_entries)} 条，{len(fit_fresh)} 条可用")

    # AI新闻
    logger.info("抓取 AI 新闻...")
    ai_entries = fetch_all_feeds("ai-news", limit_per_feed=5)
    ai_fresh = [e for e in ai_entries if str_hash(e["title"]) not in posted_titles][:limit_ai]
    logger.info(f"获取 {len(ai_entries)} 条，{len(ai_fresh)} 条可用")

    # 内容富化
    all_fresh = cb_fresh + fit_fresh + ai_fresh
    if all_fresh:
        enrich_batch(all_fresh)

    # 生成文章 (质量过滤后 None 跳过)
    for entry in cb_fresh:
        if entry.get("enriched") is not False:
            res = build_and_save(entry, "cross-border", date_str, existing_slugs)
            if res: new_posts.append(res)
    for entry in fit_fresh:
        if entry.get("enriched") is not False:
            res = build_and_save(entry, "fitness", date_str, existing_slugs)
            if res: new_posts.append(res)
    for entry in ai_fresh:
        if entry.get("enriched") is not False:
            res = build_and_save(entry, "ai-news", date_str, existing_slugs)
            if res: new_posts.append(res)

    # 补充抓取
    cb_total = sum(1 for p in new_posts if p["cat"] == "cross-border")
    fit_total = sum(1 for p in new_posts if p["cat"] == "fitness")
    ai_total = sum(1 for p in new_posts if p["cat"] == "ai-news")

    if cb_total < limit_cb or fit_total < limit_fit or ai_total < limit_ai:
        logger.info(f"补充搜索 (缺CB:{limit_cb - cb_total} Fit:{limit_fit - fit_total} AI:{limit_ai - ai_total})...")
        fill_all = fetch_fill(
            max(0, limit_cb - cb_total + limit_fit - fit_total + limit_ai - ai_total),
            posted_titles,
        )
        for entry in fill_all:
            sec = entry["section"]
            if sec == "cross-border" and cb_total < limit_cb:
                res = build_and_save(entry, "cross-border", date_str, existing_slugs)
                if res: new_posts.append(res); cb_total += 1
            elif sec == "fitness" and fit_total < limit_fit:
                res = build_and_save(entry, "fitness", date_str, existing_slugs)
                if res: new_posts.append(res); fit_total += 1
            elif sec == "ai-news" and ai_total < limit_ai:
                res = build_and_save(entry, "ai-news", date_str, existing_slugs)
                if res: new_posts.append(res); ai_total += 1

    current_total = len(load_json(JSON_PATH))
    cb_count = sum(1 for p in new_posts if p["cat"] == "cross-border")
    fit_count = sum(1 for p in new_posts if p["cat"] == "fitness")
    ai_count = sum(1 for p in new_posts if p["cat"] == "ai-news")

    logger.info(f"[DONE] {date_str} — 跨境 {cb_count} + 健身 {fit_count} + AI {ai_count} = {len(new_posts)} 篇")
    logger.info(f"线上共 {current_total} 篇文章 -> http://20020426.top")

    return new_posts
