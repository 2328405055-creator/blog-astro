# textscripts · utils/markdown_utils.py — Markdown 构建工具
# 从 daily_generator.py 抽离 build_*_post() 函数

import urllib.parse
from textscripts.utils.file_ops import today_str


def build_search_link(title: str, domain: str) -> str:
    """构建在源站搜索文章的直连"""
    q = urllib.parse.quote(title[:60])
    domain_clean = domain.replace("www.", "")
    search_templates = {
        "ebrun.com": f"https://www.ebrun.com/search?keyword={q}",
        "cifnews.com": f"https://www.cifnews.com/search?keyword={q}",
        "jiemian.com": f"https://www.jiemian.com/search/?keyword={q}",
        "sina.com.cn": f"https://search.sina.com.cn/?q={q}",
        "sohu.com": f"https://search.sohu.com/?keyword={q}",
        "163.com": f"https://search.163.com/search?keyword={q}",
    }
    for key, url in search_templates.items():
        if key in domain_clean:
            return url
    return f"https://www.google.com/search?q={q}+site:{domain_clean}"


# ============================================================
# 板块元数据
# ============================================================

CAT_NAMES_CB = {
    "selection": "选品技巧",
    "ozon": "Ozon运营",
    "yandex": "Yandex运营",
    "russia-market": "俄罗斯市场",
    "logistics": "物流收款",
    "tools": "工具教程",
}

CAT_NAMES_FIT = {
    "male": "男性训练",
    "female": "女性训练",
    "yoga-mat": "瑜伽垫动作",
    "plan": "每日计划",
    "diet": "饮食建议",
}

AI_CAT_NAMES = {
    "ai-tools": "AI工具",
    "ai-industry": "行业动态",
    "ai-ecommerce": "AI与电商",
    "ai-tutorial": "AI教程",
}


# ============================================================
# 分类逻辑
# ============================================================

def classify_cross_border(title: str) -> str:
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


def classify_fitness(title: str) -> str:
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


def classify_ai(title: str) -> str:
    t = title.lower()
    if any(w in t for w in ["工具", "tool", "应用", "platform"]):
        return "ai-tools"
    if any(w in t for w in ["电商", "跨境", "ecommerce", "零售", "卖家"]):
        return "ai-ecommerce"
    if any(w in t for w in ["教程", "指南", "tutorial", "guide", "how"]):
        return "ai-tutorial"
    return "ai-industry"


# ============================================================
# Markdown 文章构建函数
# ============================================================

def build_cross_border_post(entry: dict) -> tuple[str, str]:
    """构建跨境教程 Markdown，返回 (正文, 子分类)"""
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
        body = (
            "## 学习要点\n\n"
            "阅读这篇教程后，你将会学到：\n\n"
            "1. **实操方法:** 具体的操作步骤和落地技巧\n"
            "2. **避坑指南:** 新手常见错误及如何避免\n"
            "3. **进阶思路:** 从入门到精通的学习路径\n"
        )

    md = (
        f"# {title}\n\n"
        f"> 📂 分类: {cat_name}\n"
        f"> 📅 采集日期: {date_str}\n"
        f"> 📰 来源: **{source_name}**（{domain}）\n\n"
        f"---\n\n{body}\n\n---\n\n"
        f"## 查看原文\n\n"
        f"📎 **原文链接:** [点击查看原文]({link})\n"
        f"🔍 **站内搜索:** [在 {source_name} 站内搜索本文]({search_url})\n\n"
        f"> 📚 本文内容来自 **{source_name}**，版权归原来源所有。\n"
    )
    return md, cat


def build_fitness_post(entry: dict) -> tuple[str, str]:
    """构建健身教程 Markdown"""
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

    images = entry.get("_images", [])
    sources_info = entry.get("_sources", [])
    body = ""
    if enriched and enriched.get("content"):
        body = enriched["content"]
        if sources_info:
            body += "\n\n## 参考来源\n\n" + "\n".join(f"- {s}" for s in sources_info)
        if images:
            body += "\n\n## 配图\n\n" + "\n".join(f"![]({img})" for img in images[:3])
    else:
        body = (
            "## 训练建议\n\n"
            "无论文章中提到哪种训练方法，请牢记:\n\n"
            "- 🔹 **动作标准优先:** 宁可少做几个，也不牺牲动作质量\n"
            "- 🔹 **循序渐进:** 每周比上周多做 1-2 个就是进步\n"
            "- 🔹 **充分休息:** 肌肉在休息时生长，每周至少休息 1 天\n"
            "- 🔹 **配合饮食:** 徒手训练配合合理饮食才能看到线条变化\n"
            "- 🔹 **只需瑜伽垫:** 本文推荐的所有训练只需一张瑜伽垫即可\n"
        )

    md = (
        f"# {title}\n\n"
        f"> 💪 分类: {cat_name}\n"
        f"> 📅 采集日期: {date_str}\n"
        f"> 📰 来源: **{source_name}**\n\n"
        f"---\n\n{body}\n\n---\n\n"
        f"## 查看原文与视频教程\n\n"
        f"📎 **原文链接:** [点击查看原文]({link})\n"
        f"🔍 **搜索原文:** [在 {source_name} 站内搜索]({search_url})\n"
        f"🎬 **YouTube 视频教程:** [搜索相关训练视频]({yt_link})\n\n"
        f"> ⚠️ 训练前请评估自身状况，量力而行。\n"
    )
    return md, cat


def build_ai_post(entry: dict) -> tuple[str, str]:
    """构建 AI 学习 Markdown"""
    title = entry["title"]
    source_name = entry["source_name"]
    domain = entry["domain"]
    link = entry["link"]
    cat = classify_ai(title)
    cat_name = AI_CAT_NAMES.get(cat, "AI新闻")
    search_url = build_search_link(title, domain)
    enriched = entry.get("enriched")
    date_str = today_str()

    images = entry.get("_images", [])
    sources_info = entry.get("_sources", [])
    body = ""
    if enriched and enriched.get("content"):
        body = enriched["content"]
        if sources_info:
            body += "\n\n## 参考来源\n\n" + "\n".join(f"- {s}" for s in sources_info)
        if images:
            body += "\n\n## 配图\n\n" + "\n".join(f"![]({img})" for img in images[:3])
    else:
        body = (
            "## AI 与跨境电商的交汇\n\n"
            "无论这则 AI 新闻的具体内容是什么，对跨境电商卖家来说，AI 正在改变:\n\n"
            "- 🔹 **选品智能化:** AI 工具正在帮助卖家分析市场趋势和消费者偏好\n"
            "- 🔹 **内容生成:** 产品描述、广告文案的 AI 自动化处理\n"
            "- 🔹 **客服优化:** AI 翻译和智能客服降低跨境沟通成本\n"
            "- 🔹 **数据驱动:** 从经验决策转向 AI 辅助的数据决策\n"
        )

    md = (
        f"# {title}\n\n"
        f"> 🤖 分类: {cat_name}\n"
        f"> 📅 采集日期: {date_str}\n"
        f"> 📰 来源: **{source_name}**\n\n"
        f"---\n\n{body}\n\n---\n\n"
        f"## 查看原文\n\n"
        f"📎 **原文链接:** [点击查看原文]({link})\n"
        f"🔍 **站内搜索:** [在 {source_name} 站内搜索]({search_url})\n\n"
        f"> 📚 本文内容来自 **{source_name}**，版权归原来源所有。\n"
    )
    return md, cat
