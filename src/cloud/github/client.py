"""GitHub integration for ElectroVision projects.

Features:
- Push project files (kicad_pcb, BOM, generated code, STL) to a GitHub repo
- Pull/clone PCB projects from public GitHub repositories
- Search for open-source PCB designs on GitHub
- Create releases with exported artifacts

Requires: pip install PyGithub
"""

from pathlib import Path
from typing import Optional


class GitHubClient:
    """
    Manages GitHub integration for ElectroVision.

    Usage
    -----
    client = GitHubClient(token="ghp_...")
    client.push_project(project, repo="username/my-pcb")
    results = client.search_pcb_designs("esp32 sensor board")
    """

    def __init__(self, token: str = "") -> None:
        self._token = token
        self._gh = None

    def _ensure_connected(self) -> None:
        if self._gh:
            return
        try:
            from github import Github
            self._gh = Github(self._token) if self._token else Github()
        except ImportError:
            raise ImportError("Zainstaluj PyGithub: pip install PyGithub")

    def authenticate(self, token: str) -> dict:
        self._token = token
        self._gh = None
        self._ensure_connected()
        user = self._gh.get_user()
        return {"login": user.login, "name": user.name, "email": user.email}

    def list_repos(self) -> list[dict]:
        self._ensure_connected()
        user = self._gh.get_user()
        return [
            {"name": r.name, "full_name": r.full_name, "url": r.html_url, "private": r.private}
            for r in user.get_repos()
        ]

    def push_project(self, project_name: str, files: dict[str, str], repo_name: str, commit_msg: str = "") -> str:
        """
        Push project files to GitHub repository.

        Parameters
        ----------
        project_name : str
        files : dict — {relative_path: content_str}
        repo_name : str — "owner/repo" or "repo" (creates if not exists)
        """
        self._ensure_connected()
        user = self._gh.get_user()
        try:
            repo = self._gh.get_repo(repo_name if "/" in repo_name else f"{user.login}/{repo_name}")
        except Exception:
            repo = user.create_repo(
                repo_name.split("/")[-1],
                description=f"ElectroVision project: {project_name}",
                auto_init=True,
            )

        msg = commit_msg or f"ElectroVision: update {project_name}"
        pushed = []
        for rel_path, content in files.items():
            try:
                existing = repo.get_contents(rel_path)
                repo.update_file(rel_path, msg, content, existing.sha)
            except Exception:
                repo.create_file(rel_path, msg, content)
            pushed.append(rel_path)
        return f"Wypchnięto {len(pushed)} plików do {repo.html_url}"

    def pull_project(self, repo_full_name: str, dest_dir: str) -> list[str]:
        """Clone/download PCB project files from a GitHub repo."""
        self._ensure_connected()
        repo = self._gh.get_repo(repo_full_name)
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        downloaded = []
        contents = repo.get_contents("")
        while contents:
            item = contents.pop(0)
            if item.type == "dir":
                contents.extend(repo.get_contents(item.path))
            elif item.name.endswith((".kicad_pcb", ".kicad_sch", ".csv", ".json", ".stl", ".step", ".ino", ".py")):
                file_path = dest / item.path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(item.decoded_content)
                downloaded.append(str(file_path))
        return downloaded

    def search_pcb_designs(self, query: str, max_results: int = 20) -> list[dict]:
        """Search GitHub for PCB design repositories."""
        self._ensure_connected()
        results = self._gh.search_repositories(
            f"{query} extension:kicad_pcb",
            sort="stars",
            order="desc",
        )
        out = []
        for i, repo in enumerate(results):
            if i >= max_results:
                break
            out.append({
                "name": repo.full_name,
                "description": repo.description,
                "stars": repo.stargazers_count,
                "url": repo.html_url,
                "topics": repo.get_topics(),
            })
        return out

    def create_release(self, repo_name: str, tag: str, title: str, files: list[str]) -> str:
        """Create a GitHub release and attach artifact files."""
        self._ensure_connected()
        user = self._gh.get_user()
        repo = self._gh.get_repo(f"{user.login}/{repo_name}" if "/" not in repo_name else repo_name)
        release = repo.create_git_release(tag=tag, name=title, message=f"ElectroVision release {tag}")
        for f in files:
            p = Path(f)
            if p.exists():
                release.upload_asset(str(p), content_type="application/octet-stream")
        return release.html_url
