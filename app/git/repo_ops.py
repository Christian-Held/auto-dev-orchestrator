from __future__ import annotations

import shutil
from pathlib import Path

from git import GitCommandError, Repo
from github import GithubException

from app.core.config import get_settings
from app.core.logging import get_logger

from .github_client import get_github_client

logger = get_logger(__name__)

REPOS_DIR = Path("./data/repos")


def clone_or_update_repo(owner: str, repo_name: str, branch: str, *, force: bool = False) -> Path:
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    target_path = REPOS_DIR / f"{owner}-{repo_name}"
    settings = get_settings()

    # Build authenticated URL with GITHUB_TOKEN
    if settings.github_token:
        auth_url = f"https://{settings.github_token}@github.com/{owner}/{repo_name}.git"
    else:
        auth_url = f"https://github.com/{owner}/{repo_name}.git"

    if target_path.exists() and force:
        logger.info("removing_repo", path=str(target_path))
        shutil.rmtree(target_path)
    if target_path.exists():
        repo = Repo(target_path)
        # Update remote URL to use token authentication
        if settings.github_token:
            repo.remotes.origin.set_url(auth_url)
        repo.remotes.origin.fetch()
    else:
        repo = Repo.clone_from(auth_url, target_path)

    # Check if repo is empty (no branches)
    if not repo.branches:
        logger.info("repo_is_empty_initializing", repo=repo_name, branch=branch)
        # Create initial commit to establish branch
        readme = target_path / "README.md"
        readme.write_text(f"# {repo_name}\n\nInitialized by auto-dev-orchestrator")
        repo.index.add(["README.md"])
        repo.index.commit("Initial commit")
        repo.git.branch("-M", branch)
        repo.git.push("-u", "origin", branch)
        logger.info("repo_initialized", branch=branch)
    else:
        # Normal checkout flow for non-empty repos
        try:
            repo.git.checkout(branch)
        except GitCommandError:
            repo.git.checkout("origin/" + branch)
            repo.git.checkout('-b', branch)
    return target_path


def create_branch(repo: Repo, branch: str, base: str) -> None:
    logger.info("create_branch", branch=branch, base=base)
    if branch in repo.heads:
        repo.git.checkout(branch)
    else:
        repo.git.checkout(base)
        repo.git.checkout('-b', branch)


def commit_all(repo: Repo, message: str) -> str:
    repo.git.add(A=True)
    if not repo.is_dirty():
        logger.info("nothing_to_commit")
        return ""
    commit = repo.index.commit(message)
    logger.info("commit_created", commit=str(commit.hexsha))
    return str(commit.hexsha)


def push_branch(repo: Repo, branch: str) -> None:
    logger.info("push_branch", branch=branch)
    repo.remotes.origin.push(refspec=f"HEAD:{branch}")


def open_pull_request(job_id: str, title: str, body: str, head: str, base: str) -> str:
    settings = get_settings()
    github = get_github_client()
    repository = github.get_repo(f"{settings.github_owner}/{settings.github_repo}")
    try:
        pr = repository.create_pull(title=title, body=body, head=head, base=base)
        logger.info("pr_opened", pr_url=pr.html_url)
        return pr.html_url
    except GithubException as exc:
        logger.error("pr_failed", error=str(exc))
        raise


def merge_strategy() -> str:
    settings = get_settings()
    return settings.merge_conflict_behavior
