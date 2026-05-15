# textscripts · generators/article_writer.py — 四阶段文章生成器
#
# 流水线: Researcher → Writer → Editor → SEO Optimizer
# 输出: 带完整 Frontmatter 的 Markdown 文章
#
# 用法:
#   from textscripts.generators.article_writer import generate_article
#   result = generate_article(
#       category="cross-border",
#       topic="Ozon FBO 物流实战指南",
#       context="参考资料文本...",
#   )
#   print(result["markdown"])      # 完整文章
#   print(result["seo"])           # SEO 优化数据

import os
import re
import json
import time
import logging
from datetime import datetime

from textscripts.config import CONFIG
from textscripts.utils.llm import _get_ai_client

logger = logging.getLogger(__name__)

# ============================================================
# 板块身份映射
# ============================================================

PERSONA = {
    "cross-border": {
        "name": "跨境电商实战教练",
        "description": "帮助中国卖家在 Ozon/Yandex 平台卖货到俄罗斯",
        "site_section": "跨境教程",
    },
    "fitness": {
        "name": "徒手健身教练",
        "description": "帮助读者在家用一张瑜伽垫完成全部训练",
        "site_section": "每日健身",
    },
    "ai-news": {
        "name": "AI 学习教练",
        "description": "帮助读者掌握 AI 工具和技能，提升工作和学习效率",
        "site_section": "AI学习",
    },
    "ozon-pick": {
        "name": "俄罗斯电商选品顾问",
        "description": "帮助中国跨境卖家分析 Ozon/Wildberries 平台选品机会",
        "site_section": "Ozon选品",
    },
}

# ============================================================
# 阶段 A: Researcher — 研究提炼
# ============================================================

RESEARCHER_SYSTEM_PROMPT = """你是一位资深内容研究员，为「猫明之主小站」撰写高质量文章做准备。

你的任务：基于提供的参考资料，输出结构化的研究笔记。

== 品牌背景 ==
猫明之主小站 (20020426.top) 是一个专注于 {site_section}的博客。人设「明猫」— 专业、实用、亲切、温暖，重视数据和实操步骤。

== 输出格式（严格遵循）==

### 1. 核心要点提炼
- 列出 5-8 个最重要的发现/观点，每条 1-2 句
- 优先标注哪些来自参考资料

### 2. 重要数据和事实
- 列出所有可量化的数据（百分比、金额、时间、数量等）
- 每条数据标注来源

### 3. 潜在争议点 / 需验证信息
- 指出可能过时、矛盾或缺少权威来源的说法
- 建议如何处置（保留/删除/标注不确定性）

### 4. 适合写入文章的 5-7 个关键角度
- 每个角度一句话说明
- 标注优先级（必写/选写）

== 铁律 ==
- 只基于提供的参考资料，不编造任何信息
- 数据必须标注来源
- 如果有信息不足以支撑一篇文章，明确说明缺少什么"""


def _stage_researcher(category: str, topic: str, context: str, model: str = None) -> dict:
    """阶段 A: 研究提炼 — 从参考资料提取结构化研究笔记

    Returns:
        {"raw": "...", "key_points": [...], "facts": [...], "angles": [...]}
    """
    persona = PERSONA.get(category, PERSONA["cross-border"])
    system_prompt = RESEARCHER_SYSTEM_PROMPT.format(site_section=persona["site_section"])

    user_msg = f"""## 文章主题
{topic}

## 参考资料（RAG 检索结果）
{context[:12000] if context else "（无参考资料，请基于你的知识库提供通用指导，并标注「需用户验证」）"}

请按格式输出研究笔记。"""

    raw = _call_llm(system_prompt, user_msg, temperature=0.3, max_tokens=2500, model=model)

    # 解析结构化数据
    key_points = _extract_section(raw, "核心要点提炼", r"[-•]\s+(.+)")
    facts = _extract_section(raw, "重要数据和事实", r"[-•]\s+(.+)")
    angles = _extract_section(raw, "适合写入文章", r"[-•]\s+(.+)")

    return {"raw": raw, "key_points": key_points, "facts": facts, "angles": angles}


# ============================================================
# 阶段 B: Writer — 文章撰写
# ============================================================

WRITER_SYSTEM_PROMPT = """你是一位受欢迎的内容创作者，以「明猫」的身份为「猫明之主小站」撰写文章。

== 你的身份 ==
你是「明猫」— {persona_description}。语气专业、实用、亲切，偶尔带一点温暖的洞察。
你的每篇文章都要让读者感到「花了时间读这篇文章真值得」。

== 文章结构（必须严格遵守）==

### 引言（H1 下直接写，无需 H2 标题）
- 用一个具体场景、问题或数据 hook 住读者
- 说明这篇文章要解决什么痛点
- 简要说明文章将提供什么价值

### ## 背景与现状
- 用数据或事实说明为什么这个主题重要
- 优先使用研究笔记中的真实数据

### ## 核心方法 / 实战步骤
- 用编号列表呈现（1. 2. 3.）
- 每个步骤包含「为什么 + 怎么做 + 注意事项」
- 包含 checklist 或工具推荐

### ## 数据支持 / 案例分析
- 引用研究笔记中的具体数据
- 提供对比或案例分析

### ## 常见问题与避坑指南
- 至少 4-6 个 FAQ
- 每个问题给出清晰答案

### ## 总结与行动建议
- 提炼 3-5 条核心 takeaways
- 给出明确的下一步行动（CTA）

### ## 来源与参考
- 列出主要参考资料

== 写作要求 ==
- 总字数：1800-2800 字（中文）
- 多使用列表、加粗关键信息
- 自然融入关键词，但避免堆砌
- 每一段都有明确价值，不写废话
- 结尾要有「猫明之主」式的温暖总结句
- 数字使用半角（123），中文使用全角标点

== 铁律 ==
- 不编造数据、人名、案例
- 没有足够信息支撑时，明确说「根据现有资料尚不明确」
- 不要写「根据原文」「据参考资料」等元描述"""


def _stage_writer(category: str, topic: str, research_notes: dict, model: str = None) -> str:
    """阶段 B: 文章撰写 — 基于研究笔记写完整文章

    Returns:
        完整 Markdown 文章（不含 Frontmatter）
    """
    persona = PERSONA.get(category, PERSONA["cross-border"])
    system_prompt = WRITER_SYSTEM_PROMPT.format(
        persona_description=persona["description"]
    )

    # 构建研究摘要
    research_summary = f"""## 研究笔记

### 核心要点
{chr(10).join(f'- {p}' for p in research_notes.get('key_points', []))}

### 重要数据
{chr(10).join(f'- {f}' for f in research_notes.get('facts', []))}

### 推荐角度
{chr(10).join(f'- {a}' for a in research_notes.get('angles', []))}
"""

    user_msg = f"""## 文章信息
- 板块: {persona['site_section']}
- 主题: {topic}
- 目标字数: 1800-2800 字

{research_summary}

请根据以上研究笔记，撰写完整的 Markdown 文章（不含 Frontmatter）。"""

    return _call_llm(system_prompt, user_msg, temperature=0.7, max_tokens=4000, model=model)


# ============================================================
# 阶段 C: Editor — 严格编辑
# ============================================================

EDITOR_SYSTEM_PROMPT = """你是一位严格的编辑，为「猫明之主小站」把守内容质量。

== 你的身份 ==
你是质量把关者，不是创作者。你的任务是让文章更好，而不是重写。

== 编辑检查清单 ==

### 1. 事实准确性
- 对照研究笔记，逐条核对数据和事实
- 发现不一致或可疑数据，标注「⚠️ 需验证」
- 如果研究笔记中没有对应支撑，标注「⚠️ 无来源」

### 2. 逻辑流畅度
- 检查段落之间过渡是否自然
- 检查是否有跳跃或重复
- 调整不顺畅的句式

### 3. 品牌语气强化
- 语气是否专业 + 实用 + 亲切？
- 是否有「猫明之主」的温暖感？
- 是否避免了油腻、标题党、贩卖焦虑？

### 4. 实用细节补充
- 是否有具体的操作步骤？
- 是否需要补充 checklist？
- 是否有足够的具体工具/平台名称？

== 输出格式 ==

### 修改后的完整文章
（输出修改后的完整 Markdown）

### 修改说明
- 列出所有修改项，每条一行
- 格式: [类型] 具体修改内容

== 铁律 ==
- 不确定的事实宁可标注也不要删除
- 改动最小化，不推翻原文章结构
- 明确区分「必须改」和「建议改」"""


def _stage_editor(research_notes: dict, draft: str, model: str = None) -> dict:
    """阶段 C: 编辑 — 事实核查 + 逻辑优化 + 品牌润色

    Returns:
        {"article": "...", "changes": [...]}
    """
    # 构建事实核查参考
    facts_ref = "\n".join(f"- {f}" for f in research_notes.get("facts", []))

    user_msg = f"""## 需核查的数据
{facts_ref if facts_ref else '（无额外参考数据）'}

## 待编辑的文章
{draft[:12000]}

请按格式输出编辑后的文章和修改说明。"""

    raw = _call_llm(EDITOR_SYSTEM_PROMPT, user_msg, temperature=0.4, max_tokens=4000, model=model)

    # 分离文章和修改说明
    article = raw
    changes = []
    if "### 修改后的完整文章" in raw:
        parts = raw.split("### 修改说明")
        article = parts[0].replace("### 修改后的完整文章", "").strip()
        if len(parts) > 1:
            changes_text = parts[1].strip()
            changes = [c.strip() for c in changes_text.split("\n") if c.strip().startswith("-")]
            changes = [c.lstrip("- ").strip() for c in changes]

    return {"article": article, "changes": changes}


# ============================================================
# 阶段 D: SEO Optimizer — 搜索优化
# ============================================================

SEO_SYSTEM_PROMPT = """你是一位 SEO 优化专家，为「猫明之主小站」优化文章搜索表现。

网站: 猫明之主 (20020426.top)
定位: 跨境电商实战 · 徒手健身 · AI学习 · Ozon选品
目标读者: 中国跨境卖家 / 健身爱好者 / AI学习者

== 输出格式（严格 JSON）==

{{
  "title_options": [
    "备选标题1 (含核心关键词, ≤60字)",
    "备选标题2 (不同角度, ≤60字)",
    "备选标题3 (更具吸引力, ≤60字)"
  ],
  "best_title": "最佳标题",
  "description": "150-160字的 SEO 描述, 含关键词, 自然吸引点击",
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5", "标签6"],
  "long_tail_keywords": ["长尾词1", "长尾词2", "长尾词3", "长尾词4", "长尾词5"],
  "internal_links": [
    {{"anchor": "推荐锚文本1", "slug": "suggested-slug-1"}},
    {{"anchor": "推荐锚文本2", "slug": "suggested-slug-2"}},
    {{"anchor": "推荐锚文本3", "slug": "suggested-slug-3"}}
  ],
  "h2_suggestions": [
    "建议调整的H2标题1",
    "建议调整的H2标题2"
  ],
  "reading_time_minutes": 8,
  "slug": "url-friendly-slug"
}}

== 要求 ==
- 输出必须是合法 JSON, 不要有 markdown 代码块标记
- 标题必须包含核心关键词
- description 必须在 150-160 字之间
- tags 必须有 5-6 个, 中英文混合
- slug 使用英文和连字符"""


def _stage_seo(category: str, topic: str, article: str, model: str = None) -> dict:
    """阶段 D: SEO 优化 — 标题 + description + 标签 + 内链 + 长尾词

    Returns:
        dict 包含 title_options, description, tags, long_tail_keywords 等
    """
    persona = PERSONA.get(category, PERSONA["cross-border"])

    user_msg = f"""## 文章信息
- 板块: {persona['site_section']}
- 核心主题: {topic}
- 文章前 1500 字:
{article[:1500]}

请输出 JSON 格式的 SEO 优化数据。"""

    raw = _call_llm(SEO_SYSTEM_PROMPT, user_msg, temperature=0.3, max_tokens=1500, model=model)

    # 解析 JSON
    try:
        seo_data = json.loads(raw)
    except json.JSONDecodeError:
        # 尝试提取 JSON 块
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if json_match:
            try:
                seo_data = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                logger.warning("SEO JSON 解析失败，使用默认值")
                seo_data = _default_seo(category, topic, article)
        else:
            logger.warning("SEO 响应中未找到 JSON")
            seo_data = _default_seo(category, topic, article)

    return seo_data


def _default_seo(category: str, topic: str, article: str) -> dict:
    """SEO 降级默认值"""
    desc = article[:160].strip().replace("#", "").replace("\n", " ")
    return {
        "title_options": [topic, f"{topic} — 实战指南", f"详解{topic}"],
        "best_title": topic,
        "description": desc if len(desc) >= 100 else f"猫明之主原创：{topic}的完整指南",
        "tags": [category, "教程", "指南"],
        "long_tail_keywords": [topic],
        "internal_links": [],
        "h2_suggestions": [],
        "reading_time_minutes": max(1, len(article) // 400),
        "slug": re.sub(r"[^\w\s-]", "", topic.lower())[:60].replace(" ", "-"),
    }


# ============================================================
# Frontmatter 生成
# ============================================================

def build_frontmatter(seo: dict, category: str, date_str: str = None) -> str:
    """根据 SEO 数据构建 YAML Frontmatter

    Args:
        seo: SEO 优化数据
        category: 文章板块
        date_str: 日期 (默认今天)

    Returns:
        YAML frontmatter 字符串
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    title = seo.get("best_title", "未命名")
    description = seo.get("description", "")
    tags = seo.get("tags", [])
    slug = seo.get("slug", "article")
    reading_time = seo.get("reading_time_minutes", 8)

    # 标签按字符串输出
    tags_yaml = ", ".join(f'"{t}"' for t in tags[:6])

    return f"""---
title: "{title}"
date: "{date_str}"
category: "{category}"
tags: [{tags_yaml}]
description: "{description}"
slug: "{slug}"
reading_time: "{reading_time} 分钟"
---"""


# ============================================================
# LLM 调用包装
# ============================================================

def _call_llm(
    system_prompt: str,
    user_msg: str,
    temperature: float = 0.7,
    max_tokens: int = 2500,
    model: str = None,
) -> str:
    """调用 LLM (主模型 → 失败自动切换备用)

    Args:
        system_prompt: 系统提示
        user_msg: 用户消息
        temperature: 温度 (0.0-1.0)
        max_tokens: 最大输出 token
        model: 覆盖默认模型

    Returns:
        LLM 响应文本
    """
    for attempt, use_backup in enumerate([False, True]):
        try:
            client, default_model = _get_ai_client(use_backup)
            used_model = model or default_model
            label = "DeepSeek" if use_backup else "Qianwen"

            logger.info(f"LLM 调用 [{label}/{used_model}] t={temperature} max_t={max_tokens}")
            resp = client.chat.completions.create(
                model=used_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return resp.choices[0].message.content.strip()

        except Exception as e:
            logger.warning(f"AI 调用失败 [{label}]: {e}")
            if not use_backup and CONFIG.get("backup_api_key"):
                logger.info("切换到备用 AI...")
                time.sleep(1)
                continue

    raise RuntimeError("所有 AI 模型调用均失败")


# ============================================================
# 辅助: 从研究笔记提取结构化信息
# ============================================================

def _extract_section(text: str, heading: str, item_pattern: str) -> list[str]:
    """从研究笔记中提取某节下的列表项"""
    # 定位节
    heading_idx = text.find(heading)
    if heading_idx == -1:
        return []

    # 取该节内容 (到下一个 ### 或文本结束)
    section_text = text[heading_idx + len(heading):]
    next_heading = re.search(r"\n###\s+", section_text)
    if next_heading:
        section_text = section_text[:next_heading.start()]

    items = re.findall(item_pattern, section_text, re.MULTILINE)
    return [i.strip() for i in items if len(i.strip()) > 3]


# ============================================================
# 阶段 E: Scorer — 质量评分 (6 维度加权)
# ============================================================

def _stage_scorer(article: str, model: str = None) -> dict:
    """阶段 E: 质量评分 — 6 维度加权打分"""
    from textscripts.generators.prompts import SCORE_ARTICLE_PROMPT

    user_msg = f"请对以下文章评分:\n\n{article[:10000]}"
    raw = _call_llm(SCORE_ARTICLE_PROMPT, user_msg, temperature=0.2, max_tokens=1500, model=model)

    score_data = {}
    try:
        score_data = json.loads(raw)
    except json.JSONDecodeError:
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if json_match:
            try:
                score_data = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                return {"total": 0, "pass": False, "details": {}, "priorities": [], "raw": raw}

    weights = {"practicality": 0.25, "accuracy": 0.20, "structure": 0.15,
               "brand_voice": 0.15, "seo": 0.15, "originality": 0.10}
    weighted_total = 0
    for key, w in weights.items():
        item = score_data.get(key, {})
        if isinstance(item, dict):
            weighted_total += item.get("score", 0) * w
        elif isinstance(item, (int, float)):
            weighted_total += item * w

    total = round(weighted_total, 2)
    return {
        "total": total,
        "pass": total >= 8.0,
        "details": score_data,
        "priorities": score_data.get("revision_priority", []),
        "raw": raw,
    }


def _revise_article(article: str, score_result: dict, model: str = None) -> str:
    """基于评分反馈修改文章"""
    from textscripts.generators.prompts import REVISION_PROMPT

    details = score_result.get("details", {})
    overall = details.get("overall_comment", "无评价")
    priorities = "\n".join(f"- {p}" for p in score_result.get("priorities", []))

    user_msg = REVISION_PROMPT.format(
        article=article[:12000],
        total=score_result["total"],
        pass_result=score_result["pass"],
        comment=overall,
        priorities=priorities or "- 整体优化",
    )
    return _call_llm(
        "你是一位专业的内容修改专家，根据评分反馈精准修改文章。",
        user_msg, temperature=0.4, max_tokens=4000, model=model,
    )


# ============================================================
# 主函数: 五阶段文章生成 (含自动迭代)
# ============================================================

def generate_article(
    category: str,
    topic: str,
    context: str = "",
    date_str: str = None,
    stages: list[str] | None = None,
    model: str = None,
    verbose: bool = True,
    max_iterations: int = 3,
    min_score: float = 8.0,
) -> dict:
    """四阶段文章生成主函数

    流水线:
      A. Researcher  — 研究提炼 (事实 + 数据 + 角度)
      B. Writer      — 文章撰写 (1800-2800 字)
      C. Editor      — 严格编辑 (事实核查 + 品牌润色)
      D. SEO Optimizer — 搜索优化 (标题/描述/标签/内链)

    Args:
        category: 板块 — cross-border | fitness | ai-news | ozon-pick
        topic: 文章主题/关键词 (如 "Ozon FBO 物流避坑指南")
        context: 参考资料 (RAG 检索结果、URL 内容、数据等)
        date_str: 发布日期 (默认今天)
        stages: 指定只运行的阶段列表，如 ["A", "B"]。默认全部
        model: LLM 模型覆盖
        verbose: True 时打印每阶段耗时

    Returns:
        {
            "markdown": "完整文章 (含 frontmatter)",
            "frontmatter": "---\n...\n---",
            "body": "文章正文 (不含 frontmatter)",
            "research": {"key_points": [...], "facts": [...], "angles": [...]},
            "editor_changes": [...],
            "seo": {"title_options": [...], "description": "...", "tags": [...], ...},
            "stats": {"category": "...", "topic": "...", "word_count": N, "stages_run": [...]},
        }
    """
    if category not in PERSONA:
        raise ValueError(f"未知板块: {category}，可选: {list(PERSONA.keys())}")

    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    stages = stages or ["A", "B", "C", "D", "E"]
    stats = {"category": category, "topic": topic, "stages_run": stages, "word_count": 0}

    result = {
        "markdown": "", "frontmatter": "", "body": "",
        "research": {}, "editor_changes": [], "seo": {}, "score": {},
        "stats": stats,
    }

    # ---- 阶段 A: Researcher ----
    if "A" in stages:
        t0 = time.time()
        logger.info(f"[阶段A] 研究: {topic[:50]}...")
        result["research"] = _stage_researcher(category, topic, context, model=model)
        if verbose:
            logger.info(f"[阶段A] 完成 ({time.time() - t0:.1f}s)")
    else:
        result["research"] = {"key_points": [], "facts": [], "angles": [], "raw": ""}

    # ---- 阶段 B: Writer ----
    if "B" in stages:
        t0 = time.time()
        logger.info(f"[阶段B] 撰写: {topic[:50]}...")
        result["body"] = _stage_writer(category, topic, result["research"], model=model)
        stats["word_count"] = len(result["body"])
        if verbose:
            logger.info(f"[阶段B] 完成 ({time.time() - t0:.1f}s) — {stats['word_count']} 字")
    elif not result["body"]:
        result["body"] = topic

    # ---- 阶段 C: Editor ----
    if "C" in stages and result["body"]:
        t0 = time.time()
        logger.info("[阶段C] 编辑...")
        edited = _stage_editor(result["research"], result["body"], model=model)
        result["body"] = edited["article"]
        result["editor_changes"] = edited["changes"]
        stats["word_count"] = len(result["body"])
        if verbose:
            logger.info(f"[阶段C] 完成 ({time.time() - t0:.1f}s)")

    # ---- 阶段 D: SEO Optimizer ----
    if "D" in stages and result["body"]:
        t0 = time.time()
        logger.info("[阶段D] SEO 优化...")
        result["seo"] = _stage_seo(category, topic, result["body"], model=model)
        if verbose:
            logger.info(f"[阶段D] 完成 ({time.time() - t0:.1f}s)")
    elif "D" in stages:
        result["seo"] = _default_seo(category, topic, "")

    # ---- 阶段 E: Scorer + 自动迭代 ----
    score_result = {"total": 0, "pass": False, "details": {}, "priorities": [], "iterations": 0}

    if "E" in stages and result["body"]:
        for iteration in range(1, max_iterations + 1):
            t0 = time.time()
            logger.info(f"[阶段E] 评分 (第 {iteration}/{max_iterations} 轮)...")
            score_result = _stage_scorer(result["body"], model=model)
            score_result["iterations"] = iteration - 1

            if verbose:
                s = "通过" if score_result["pass"] else "未通过"
                logger.info(f"[阶段E] {s} — {score_result['total']}/10")

            if score_result["pass"]:
                break

            if iteration < max_iterations:
                logger.info(f"[阶段E] 修改 (分数 {score_result['total']} < {min_score})...")
                result["body"] = _revise_article(result["body"], score_result, model=model)
                stats["word_count"] = len(result["body"])
            else:
                logger.warning(f"[阶段E] 已达最大迭代次数 ({max_iterations})，最终分数 {score_result['total']}")

    result["score"] = score_result

    # ---- 组装最终 Markdown ----
    result["frontmatter"] = build_frontmatter(result["seo"], category, date_str)
    result["markdown"] = f"{result['frontmatter']}\n\n{result['body']}"
    stats["word_count"] = len(result["body"])

    if verbose:
        s = f", 评分 {score_result['total']}/10" if score_result["total"] > 0 else ""
        logger.info(f"文章生成完成: {stats['word_count']} 字{s}")

    return result


# ============================================================
# 便捷函数: 保存文章
# ============================================================

def save_article(result: dict, posts_dir: str = None) -> str:
    """将生成的文章保存为 Markdown 文件 + 更新 posts.json

    Args:
        result: generate_article() 的返回值
        posts_dir: posts 目录 (默认 textscripts.config.POSTS_DIR)

    Returns:
        保存的 slug
    """
    from textscripts.config import POSTS_DIR, JSON_PATH
    from textscripts.utils.file_ops import save_json, load_json

    slug = result["seo"].get("slug", "article")
    date_str = result["stats"].get("date", datetime.now().strftime("%Y-%m-%d"))
    category = result["stats"]["category"]
    title = result["seo"].get("best_title", "未命名")
    description = result["seo"].get("description", "")
    tags = result["seo"].get("tags", [])

    target_dir = posts_dir or POSTS_DIR
    os.makedirs(target_dir, exist_ok=True)

    # 写入 .md
    md_path = os.path.join(target_dir, f"{slug}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(result["markdown"])
    logger.info(f"文章已保存: {md_path}")

    # 更新 posts.json
    posts = load_json(JSON_PATH)
    # 移除同 slug 旧条目
    posts = [p for p in posts if p.get("slug") != slug]
    posts.insert(0, {
        "slug": slug,
        "title": title,
        "date": date_str,
        "lastmod": date_str,
        "excerpt": result["body"][:300],
        "cat": category,
        "sub": tags[0] if tags else "",
        "source": "猫明之主原创",
        "source_name": "猫明之主",
        "has_content": True,
        "word_count": result["stats"]["word_count"],
    })
    save_json(JSON_PATH, posts)
    logger.info(f"posts.json 更新: {len(posts)} 篇文章")

    return slug

