# textscripts · utils/llm.py — AI 调用 (总结 + 翻译)

import re
import logging
from openai import OpenAI

from textscripts.config import CONFIG

logger = logging.getLogger(__name__)


def _get_ai_client(use_backup=False):
    """获取 AI 客户端 (主: 千问, 备: DeepSeek)"""
    if use_backup:
        return (
            OpenAI(
                api_key=CONFIG["backup_api_key"],
                base_url=CONFIG["backup_api_base"],
            ),
            CONFIG["backup_model"],
        )
    return (
        OpenAI(
            api_key=CONFIG["primary_api_key"],
            base_url=CONFIG["primary_api_base"],
        ),
        CONFIG["primary_model"],
    )


def summarize_article(title, source_name, content_md, section):
    """用 AI 总结文章为高质量学习内容"""
    if not content_md or len(content_md) < 100:
        return None

    prompts = {
        "cross-border": (
            "你是一位跨境电商实战教练，帮助中国卖家在Ozon/Yandex平台卖货到俄罗斯。"
            "把下面的文章总结为一篇600-900字的纯中文教程。要求：\n"
            "1. 用 ## 分节，每节有实质性内容\n"
            "2. 包含具体操作步骤、工具名称、数据指标\n"
            "3. 指出新手常见的3个错误及如何避免\n"
            "4. 结尾给一个「今日行动建议」\n"
            "只输出教程正文，不要写「根据原文」之类的元描述。"
        ),
        "fitness": (
            "你是一位徒手健身教练，帮助读者在家用瑜伽垫训练。"
            "把下面的文章总结为一篇600-900字的纯中文健身教程。要求：\n"
            "1. 用 ## 分节，每节有实质性内容\n"
            "2. 包含具体动作名称、组数次数、动作要领\n"
            "3. 指出常见的动作错误及纠正方法\n"
            "4. 结尾给一个「今日训练计划」\n"
            "只输出教程正文，不要写「根据原文」之类的元描述。"
        ),
        "ai-news": (
            "你是一位AI学习教练，帮助读者掌握AI工具和技能。"
            "把下面的文章总结为一篇600-900字的纯中文学习教程。要求：\n"
            "1. 用 ## 分节，每节有实质性内容\n"
            "2. 包含具体工具名称、使用步骤、参数设置\n"
            "3. 指出实际应用场景和效率提升点\n"
            "4. 结尾给一个「今日动手实践」任务\n"
            "只输出教程正文，不要写「根据原文」之类的元描述。"
        ),
    }

    system_prompt = prompts.get(section, prompts["cross-border"])
    user_msg = f"标题：{title}\n来源：{source_name}\n\n原文内容：\n{content_md[:6000]}"

    for attempt, use_backup in enumerate([False, True]):
        try:
            import time

            client, model = _get_ai_client(use_backup)
            label = "DeepSeek" if use_backup else "Qianwen"
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=2000,
                temperature=0.7,
            )
            body = resp.choices[0].message.content.strip()
            key_points = re.findall(r"^##\s+(.+)", body, re.MULTILINE)[:5]
            if not key_points:
                key_points = re.findall(r"^\d+\.\s+(.+)", body, re.MULTILINE)[:5]
            return {
                "content": body,
                "key_points": key_points if key_points else ["详见正文"],
                "word_count": len(body),
                "model": label,
            }
        except Exception as e:
            logger.warning(f"AI 调用失败 [{label}]: {e}")
            if not use_backup and CONFIG.get("backup_api_key"):
                logger.info("切换到备用 AI...")
                time.sleep(1)
                continue
    return None


def translate_title(title):
    """如果标题主要是英文，翻译为中文"""
    en_chars = len(re.findall(r"[a-zA-Z]", title))
    cn_chars = len(re.findall(r"[一-鿿]", title))
    if en_chars <= cn_chars or en_chars < 15:
        return title

    try:
        client, model = _get_ai_client(False)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": f"把这句话翻译成简洁的中文标题（不要加任何前缀或编号）: {title}",
                }
            ],
            max_tokens=80,
            temperature=0.3,
        )
        cn = resp.choices[0].message.content.strip()
        if cn and len(cn) >= 3 and not cn.startswith("1."):
            return cn
    except Exception as e:
        logger.warning(f"翻译失败: {e}")
    return title
