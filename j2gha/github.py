"""Small GitHub REST client: token discovery, on-disk GET cache and rate-limit handling."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

from .config import CACHE_DIR, offline

API = "https://api.github.com"
API_VERSION = "2022-11-28"


class GitHubError(RuntimeError):
    def __init__(self, status: int, message: str, url: str):
        super().__init__(f"GitHub API {status} for {url}: {message}")
        self.status = status
        self.url = url


class OfflineError(GitHubError):
    """A request J2GHA_OFFLINE stopped: it was not in the cache."""

    def __init__(self, url: str):
        super().__init__(0, "not cached, and J2GHA_OFFLINE is set", url)


def discover_token() -> str | None:
    for var in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


class GitHub:
    """GET-centric client. Search calls are throttled to the code-search limit (10/min)."""

    def __init__(self, token: str | None = None, cache_ttl: int = 24 * 3600, verbose: bool = False):
        self.token = token or discover_token()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "j2gha-harness",
            }
        )
        if self.token:
            self.session.headers["Authorization"] = f"Bearer {self.token}"
        self.cache_dir = CACHE_DIR / "github"
        self.cache_ttl = cache_ttl
        self.verbose = verbose
        self._last_search = 0.0
        self.search_interval = 6.5  # code search: 10 requests/minute when authenticated

    # ------------------------------------------------------------------ helpers
    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[github] {msg}", file=sys.stderr)

    def _cache_path(self, url: str, params: dict | None) -> Path:
        key = url + "?" + json.dumps(params or {}, sort_keys=True)
        digest = hashlib.sha256(key.encode()).hexdigest()
        return self.cache_dir / digest[:2] / f"{digest}.json"

    def _read_cache(self, path: Path) -> Any | None:
        if self.cache_ttl <= 0 or not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self.cache_ttl:
            return None
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def _write_cache(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def request(self, method: str, path: str, *, params: dict | None = None, json_body: Any = None,
                use_cache: bool = True, headers: dict | None = None, raw: bool = False) -> Any:
        url = path if path.startswith("http") else f"{API}{path}"
        cacheable = method == "GET" and use_cache and not raw
        cache_file = self._cache_path(url, params) if cacheable else None
        if cache_file:
            cached = self._read_cache(cache_file)
            if cached is not None:
                return cached
        if offline():
            raise OfflineError(url)
        if "/search/" in url:
            wait = self.search_interval - (time.time() - self._last_search)
            if wait > 0:
                time.sleep(wait)
            self._last_search = time.time()
        for attempt in range(6):
            self._log(f"{method} {url} {params or ''}")
            try:
                resp = self.session.request(method, url, params=params, json=json_body, headers=headers, timeout=60)
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt >= 3:
                    raise
                print(f"[github] {type(e).__name__} for {method} {url}; retrying in {2 ** attempt}s", file=sys.stderr)
                time.sleep(2 ** attempt)
                continue
            if resp.status_code in (403, 429) and self._rate_limited(resp):
                delay = self._retry_delay(resp, attempt)
                print(f"[github] rate limited; sleeping {delay:.0f}s", file=sys.stderr)
                time.sleep(delay)
                continue
            if resp.status_code >= 500 and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            break
        if resp.status_code >= 400:
            try:
                message = resp.json().get("message", resp.text[:200])
            except ValueError:
                message = resp.text[:200]
            raise GitHubError(resp.status_code, message, url)
        if raw:
            return resp
        data = resp.json() if resp.content else None
        if cache_file is not None:
            self._write_cache(cache_file, data)
        return data

    @staticmethod
    def _rate_limited(resp: requests.Response) -> bool:
        if resp.status_code == 429:
            return True
        if resp.headers.get("x-ratelimit-remaining") == "0":
            return True
        try:
            return "rate limit" in resp.json().get("message", "").lower()
        except ValueError:
            return False

    @staticmethod
    def _retry_delay(resp: requests.Response, attempt: int) -> float:
        if resp.headers.get("retry-after"):
            return float(resp.headers["retry-after"]) + 1
        reset = resp.headers.get("x-ratelimit-reset")
        if reset and resp.headers.get("x-ratelimit-remaining") == "0":
            return max(5.0, float(reset) - time.time() + 2)
        return min(120.0, 15.0 * (attempt + 1))

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    # ------------------------------------------------------------- endpoints
    def search_code(self, query: str, per_page: int = 30, page: int = 1) -> dict:
        return self.get("/search/code", params={"q": query, "per_page": per_page, "page": page})

    def repo(self, full_name: str) -> dict:
        return self.get(f"/repos/{full_name}")

    def owner_repos(self, owner: str) -> list[dict]:
        """Public repositories owned by a user or organisation (``/users/{owner}/repos`` serves both)."""
        repos: list[dict] = []
        page = 1
        while True:
            batch = self.get(f"/users/{owner}/repos", params={"type": "owner", "per_page": 100, "page": page})
            repos += batch
            if len(batch) < 100:
                return repos
            page += 1

    def tree(self, full_name: str, ref: str) -> dict:
        return self.get(f"/repos/{full_name}/git/trees/{ref}", params={"recursive": "1"})

    def blob_text(self, full_name: str, sha: str) -> str:
        data = self.get(f"/repos/{full_name}/git/blobs/{sha}")
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return data.get("content", "")

    def last_commit_for_path(self, full_name: str, path: str, ref: str | None = None) -> dict | None:
        params = {"path": path, "per_page": 1}
        if ref:
            params["sha"] = ref
        commits = self.get(f"/repos/{full_name}/commits", params=params)
        return commits[0] if commits else None

    def authenticated_login(self) -> str:
        return self.get("/user", use_cache=False)["login"]
