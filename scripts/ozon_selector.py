#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ozon俄罗斯站每日选品推荐 — thin wrapper，实际逻辑在 textscripts/ 包中

用法:
  python scripts/ozon_selector.py              # 采集+生成(不推送)
  python scripts/ozon_selector.py --push       # 采集+生成+git推送
  python scripts/ozon_selector.py --dry-run    # 仅采集预览,不写文件
"""

import sys
import os
import logging
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from textscripts.generators.ozon_generator import run_selector
from textscripts.publishers.git_publisher import publish as git_publish
from textscripts.utils.file_ops import load_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ozon_config.json")


def main():
    do_push = "--push" in sys.argv
    dry_run = "--dry-run" in sys.argv

    config = load_json(CONFIG_PATH)
    if not config:
        logger.error("无法加载配置文件: scripts/ozon_config.json")
        sys.exit(1)

    if not config.get("enabled", True):
        logger.info("Ozon selector 已在配置中禁用")
        return

    run_selector(config, dry_run=dry_run)

    if do_push and not dry_run:
        result = git_publish(BASE_DIR, commit_prefix="Ozon每日选品", dry_run=False)
        if result["pushed"]:
            logger.info(f"推送完成: {result['commit_hash']}")
        elif result["error"]:
            logger.error(f"推送失败: {result['error']}")
        else:
            logger.info("推送跳过（无变更）")


if __name__ == "__main__":
    main()
