# textscripts · generators/unified_generator.py — 统一调度 4 个板块

import logging
from textscripts.generators.daily_generator import generate_posts
from textscripts.generators.ozon_generator import run_selector
from textscripts.utils.file_ops import today_str

logger = logging.getLogger(__name__)


def generate_section(section: str, **kwargs) -> dict:
    """按板块生成内容

    Args:
        section: cross-border | fitness | ai-news | ozon-pick | all
        **kwargs: 传递给底层生成器的额外参数
            - config (dict): ozon 配置 (仅 ozon-pick)
            - dry_run (bool): ozon 预览模式 (仅 ozon-pick)
            - limit_cb / limit_fit / limit_ai (int): 每日生成数量

    Returns:
        {"section": str, "count": int, "date": str}
    """
    date_str = today_str()

    if section == "ozon-pick":
        config = kwargs.get("config")
        if config is None:
            from textscripts.config import SCRIPTS_DIR
            from textscripts.utils.file_ops import load_json as _load
            import os
            config_path = os.path.join(SCRIPTS_DIR, "ozon_config.json")
            config = _load(config_path) if os.path.exists(config_path) else {}

        dry_run = kwargs.get("dry_run", False)
        result = run_selector(config, dry_run=dry_run)
        count = len(result.get("products", [])) if result else 0
        return {"section": "ozon-pick", "count": count, "date": date_str}

    elif section in ("cross-border", "fitness", "ai-news"):
        limit_cb = kwargs.get("limit_cb", 4)
        limit_fit = kwargs.get("limit_fit", 3)
        limit_ai = kwargs.get("limit_ai", 3)
        posts = generate_posts(limit_cb=limit_cb, limit_fit=limit_fit, limit_ai=limit_ai)
        count = sum(1 for p in posts if p.get("cat") == section)
        return {"section": section, "count": count, "date": date_str}

    elif section == "all":
        total = 0
        # 三板块
        try:
            posts = generate_posts(
                limit_cb=kwargs.get("limit_cb", 4),
                limit_fit=kwargs.get("limit_fit", 3),
                limit_ai=kwargs.get("limit_ai", 3),
            )
            total += len(posts)
        except Exception as e:
            logger.error(f"三板块生成失败: {e}")

        # Ozon
        try:
            config = kwargs.get("config")
            if config is None:
                from textscripts.config import SCRIPTS_DIR
                from textscripts.utils.file_ops import load_json as _load
                import os
                config_path = os.path.join(SCRIPTS_DIR, "ozon_config.json")
                config = _load(config_path) if os.path.exists(config_path) else {}
            dry_run = kwargs.get("dry_run", False)
            result = run_selector(config, dry_run=dry_run)
            if result:
                total += len(result.get("products", []))
        except Exception as e:
            logger.error(f"Ozon 生成失败: {e}")

        return {"section": "all", "count": total, "date": date_str}

    else:
        raise ValueError(f"未知板块: {section}")
