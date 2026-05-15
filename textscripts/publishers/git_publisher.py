# textscripts · publishers/git_publisher.py — Git 操作（从 cli.py 和 ozon_selector.py 抽离）

import subprocess
import logging
from textscripts.utils.file_ops import today_str

logger = logging.getLogger(__name__)


def git_add_all(repo_dir: str) -> tuple[bool, str]:
    """git add .  — 返回 (成功, 输出)"""
    r = subprocess.run(
        ["git", "add", "."],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    ok = r.returncode == 0
    if not ok:
        logger.error(f"git add 失败: {r.stderr[:120]}")
    return ok, r.stderr if not ok else ""


def git_commit(repo_dir: str, message: str) -> tuple[bool, str]:
    """git commit  — 返回 (成功, commit hash 或错误信息)"""
    r = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    ok = r.returncode == 0
    if ok:
        # 提取 commit hash
        hash_r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        return True, hash_r.stdout.strip()
    # "nothing to commit" 不算失败
    if "nothing to commit" in r.stdout or "nothing to commit" in r.stderr:
        return True, "(无变更)"
    logger.error(f"git commit 失败: {r.stderr[:120]}")
    return False, r.stderr[:120]


def git_push(repo_dir: str) -> tuple[bool, str]:
    """git push  — 返回 (成功, 输出)"""
    r = subprocess.run(
        ["git", "push"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    ok = r.returncode == 0
    if not ok:
        logger.error(f"git push 失败: {r.stderr[:120]}")
    return ok, r.stderr if not ok else r.stdout


def publish(repo_dir: str, commit_prefix: str = "每日更新", dry_run: bool = False) -> dict:
    """执行完整的 git add → commit → push 流程

    Args:
        repo_dir: 仓库根目录
        commit_prefix: commit 消息前缀
        dry_run: True 时只打印不执行

    Returns:
        {"pushed": bool, "commit_hash": str, "error": str}
    """
    if dry_run:
        logger.info("[DRY-RUN] 跳过 git 操作")
        return {"pushed": False, "commit_hash": "(dry-run)", "error": ""}

    commit_msg = f"{commit_prefix} {today_str()} — 来源采集"
    logger.info(f"Git 发布: {commit_msg}")

    ok, err = git_add_all(repo_dir)
    if not ok:
        return {"pushed": False, "commit_hash": "", "error": f"add: {err}"}

    ok, commit_hash = git_commit(repo_dir, commit_msg)
    if not ok:
        return {"pushed": False, "commit_hash": "", "error": f"commit: {commit_hash}"}

    if commit_hash == "(无变更)":
        logger.info("无变更，跳过 push")
        return {"pushed": False, "commit_hash": "", "error": ""}

    ok, err = git_push(repo_dir)
    if not ok:
        return {"pushed": False, "commit_hash": commit_hash, "error": f"push: {err}"}

    logger.info(f"推送完成: {commit_hash}")
    return {"pushed": True, "commit_hash": commit_hash, "error": ""}
