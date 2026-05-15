# textscripts · publishers/site_publisher.py — 统一发布入口

import logging
from textscripts.config import BASE_DIR
from textscripts.publishers.git_publisher import publish as git_publish
from textscripts.utils.sitemap_generator import generate_sitemap
from textscripts.utils.file_ops import today_str

logger = logging.getLogger(__name__)


def publish_site(
    push: bool = False,
    dry_run: bool = True,
    commit_prefix: str = "每日更新",
) -> dict:
    """统一发布流程：更新 sitemap + 可选 git push

    Args:
        push: True 执行 git push
        dry_run: True 仅预览不实际操作
        commit_prefix: commit 消息前缀

    Returns:
        {"sitemap": bool, "pushed": bool, "commit_hash": str, "errors": list}
    """
    errors = []
    sitemap_ok = False
    pushed = False
    commit_hash = ""

    if dry_run:
        logger.info("[DRY-RUN] 发布预览模式")

    # 1. 更新 sitemap
    try:
        if not dry_run:
            generate_sitemap()
        sitemap_ok = True
        logger.info("Sitemap 更新完成 (或 dry-run)")
    except Exception as e:
        errors.append(f"sitemap: {e}")
        logger.error(f"Sitemap 生成失败: {e}")

    # 2. Git push
    if push and not dry_run:
        result = git_publish(BASE_DIR, commit_prefix=commit_prefix, dry_run=False)
        pushed = result["pushed"]
        commit_hash = result["commit_hash"]
        if result["error"]:
            errors.append(result["error"])
    elif push and dry_run:
        logger.info("[DRY-RUN] 跳过 git push")

    return {
        "sitemap": sitemap_ok,
        "pushed": pushed,
        "commit_hash": commit_hash,
        "errors": errors,
    }
