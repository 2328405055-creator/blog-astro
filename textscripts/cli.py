# textscripts · cli.py — 命令行入口

import sys
import os
import logging

from textscripts.config import BASE_DIR, POSTS_DIR, JSON_PATH, SCRIPTS_DIR
from textscripts.generators.daily_generator import generate_posts
from textscripts.generators.unified_generator import generate_section
from textscripts.utils.sitemap_generator import generate_sitemap
from textscripts.utils.file_ops import load_json, today_str
from textscripts.publishers.git_publisher import publish as git_publish

logger = logging.getLogger(__name__)

# 板块映射
SECTION_MAP = {
    "cb": "cross-border",
    "fit": "fitness",
    "ai": "ai-news",
    "ozon": "ozon-pick",
    "all": "all",
}


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args():
    """解析命令行参数

    Returns:
        {"section": "all", "push": False, "dry_run": False}
    """
    args = {"section": "all", "push": False, "dry_run": False}

    for i, arg in enumerate(sys.argv):
        if arg == "--section" and i + 1 < len(sys.argv):
            raw = sys.argv[i + 1]
            args["section"] = SECTION_MAP.get(raw, raw)
        elif arg == "--push":
            args["push"] = True
        elif arg == "--dry-run":
            args["dry_run"] = True

    return args


def load_ozon_config():
    """加载 Ozon 配置"""
    import os as _os
    config_path = _os.path.join(SCRIPTS_DIR, "ozon_config.json")
    if _os.path.exists(config_path):
        return load_json(config_path)
    return {}


def main():
    setup_logging()
    args = parse_args()

    section = args["section"]
    do_push = args["push"]
    dry_run = args["dry_run"]

    logger.info("=" * 56)
    logger.info(f"  猫明之主内容生成器 v5 — {section}")
    logger.info("=" * 56)

    if not os.path.exists(POSTS_DIR):
        os.makedirs(POSTS_DIR)

    # 生成内容
    if section == "all":
        # 向后兼容：使用原有 generate_posts() 逻辑
        try:
            generate_posts()
        except Exception as e:
            logger.error(f"三板块生成失败: {e}", exc_info=True)

        # Ozon 板块
        try:
            config = load_ozon_config()
            if config.get("enabled", True):
                generate_section("ozon-pick", config=config, dry_run=dry_run)
        except Exception as e:
            logger.error(f"Ozon 生成失败: {e}", exc_info=True)

    elif section == "ozon-pick":
        config = load_ozon_config()
        if not config.get("enabled", True):
            logger.info("Ozon selector 已在配置中禁用")
            return
        try:
            generate_section("ozon-pick", config=config, dry_run=dry_run)
        except Exception as e:
            logger.error(f"Ozon 生成失败: {e}", exc_info=True)

    else:
        # 单个板块 (cross-border / fitness / ai-news)
        try:
            generate_section(section)
        except Exception as e:
            logger.error(f"{section} 生成失败: {e}", exc_info=True)

    # Sitemap
    try:
        generate_sitemap()
    except Exception as e:
        logger.error(f"Sitemap 生成失败: {e}", exc_info=True)

    # Git push
    if do_push and not dry_run:
        result = git_publish(BASE_DIR, commit_prefix="每日更新", dry_run=False)
        if result["pushed"]:
            logger.info(f"推送完成: {result['commit_hash']}")
        elif result["error"]:
            logger.error(f"推送失败: {result['error']}")
        else:
            logger.info("推送跳过（无变更）")

    total = len(load_json(JSON_PATH))
    logger.info(f"当前线上 {total} 篇文章 -> http://20020426.top")


if __name__ == "__main__":
    main()
