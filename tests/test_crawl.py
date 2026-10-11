"""Crawler snapshot consistency: blob, text, file history and citation all come from one commit (fake GitHub)."""

import json
from urllib.parse import unquote

import pytest
from conftest import load

import j2gha.crawl.crawler as crawler
from j2gha.github import GitHubError

REPO = "acme/app"
PATH = "ci/Jenkins file"  # a space, to exercise URL quoting
HEAD = "c2c2c2c2c2c2c2c2c2c2c2c2c2c2c2c2c2c2c2c2"
STALE_BLOB = "b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1"  # what the code-search index still reports
SNAPSHOT_BLOB = "b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2"  # what the branch head holds


class FakeGitHub:
    """Code search lags the branch: it reports STALE_BLOB, the head commit holds SNAPSHOT_BLOB."""

    token = "fake"
    tree_blob: str | None = SNAPSHOT_BLOB
    calls: list[tuple] = []

    def __init__(self, *_a, **_k):
        FakeGitHub.calls = []
        self.text = load("declarative")[0]

    def search_code(self, q, per_page=30, page=1):
        return {"total_count": 1, "items": [{"repository": {"full_name": REPO}, "path": PATH, "sha": STALE_BLOB,
                                             "html_url": f"https://github.com/{REPO}/blob/main/{PATH}"}]}

    def repo(self, full):
        return {"full_name": full, "html_url": f"https://github.com/{full}", "license": {"spdx_id": "MIT"},
                "default_branch": "main", "stargazers_count": 5, "forks_count": 1, "archived": False,
                "pushed_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-01T00:00:00Z",
                "created_at": "2020-01-01T00:00:00Z"}

    def get(self, path, params=None, use_cache=True):
        FakeGitHub.calls.append(("get", unquote(path), params, use_cache))
        if path == f"/repos/{REPO}/git/ref/heads/main":
            return {"ref": "refs/heads/main", "object": {"type": "commit", "sha": HEAD}}
        if unquote(path) == f"/repos/{REPO}/contents/{PATH}" and params == {"ref": HEAD}:
            if self.tree_blob is None:
                raise GitHubError(404, "Not Found", path)
            return {"type": "file", "path": PATH, "sha": self.tree_blob}
        raise AssertionError(f"unexpected GET {path} {params}")

    def blob_text(self, full, sha):
        FakeGitHub.calls.append(("blob_text", sha))
        assert sha == SNAPSHOT_BLOB, "text must come from the snapshot's blob, not the stale search hit"
        return self.text

    def last_commit_for_path(self, full, path, ref=None):
        FakeGitHub.calls.append(("last_commit_for_path", path, ref))
        return {"sha": "f1f1f1f1", "commit": {"committer": {"date": "2026-09-30T00:00:00Z"}}}


@pytest.fixture
def fake_crawl(monkeypatch, tmp_path):
    text, ast = load("declarative")
    monkeypatch.setattr(crawler, "GitHub", FakeGitHub)
    monkeypatch.setattr(crawler, "list_example_ids", lambda: [])
    monkeypatch.setattr(crawler, "dump_sources", lambda sources: {k: ast for k in sources})  # no Docker
    monkeypatch.setattr(FakeGitHub, "tree_blob", SNAPSHOT_BLOB)
    return tmp_path


def test_crawl_reads_everything_from_one_snapshot(fake_crawl):
    written = crawler.crawl(1, out_dir=fake_crawl, styles=["declarative"])
    assert len(written) == 1
    meta = json.loads((fake_crawl / "001" / "source.json").read_text())
    # the branch head is resolved once, bypassing the 24h GET cache
    ref_calls = [c for c in FakeGitHub.calls if c[0] == "get" and "/git/ref/" in c[1]]
    assert ref_calls == [("get", f"/repos/{REPO}/git/ref/heads/main", None, False)]
    assert meta["snapshot_commit"] == HEAD
    assert meta["blob_sha"] == SNAPSHOT_BLOB and meta["discovered_blob_sha"] == STALE_BLOB
    # history is anchored to the snapshot commit, not re-resolved from the branch name
    assert ("last_commit_for_path", PATH, HEAD) in FakeGitHub.calls
    assert meta["file_last_commit_sha"] == "f1f1f1f1"  # kept: full-mode runs check it out
    assert meta["file_url"] == f"https://github.com/{REPO}/blob/{HEAD}/{PATH}"
    assert (fake_crawl / "001" / "Jenkinsfile").read_text() == load("declarative")[0]


def test_crawl_matching_blob_records_no_discovery_drift(fake_crawl, monkeypatch):
    monkeypatch.setattr(FakeGitHub, "search_code", lambda self, q, per_page=30, page=1: {
        "total_count": 1, "items": [{"repository": {"full_name": REPO}, "path": PATH, "sha": SNAPSHOT_BLOB,
                                     "html_url": ""}]})
    crawler.crawl(1, out_dir=fake_crawl, styles=["declarative"])
    meta = json.loads((fake_crawl / "001" / "source.json").read_text())
    assert meta["blob_sha"] == SNAPSHOT_BLOB and meta["snapshot_commit"] == HEAD
    assert "discovered_blob_sha" not in meta


def test_crawl_drops_file_missing_from_snapshot(fake_crawl, monkeypatch):
    monkeypatch.setattr(FakeGitHub, "tree_blob", None)  # deleted/renamed since the search index was built
    assert crawler.crawl(1, out_dir=fake_crawl, styles=["declarative"]) == []
    assert not any(c[0] == "blob_text" for c in FakeGitHub.calls)
    assert not (fake_crawl / "001").exists()


def test_next_index_skips_the_twins(monkeypatch, tmp_path):
    # examples/1NN are local twins of 0NN (jenkins-example-twin): crawled examples keep counting below 100
    monkeypatch.setattr(crawler, "list_example_ids", lambda: ["001", "002", "020", "104", "112", "119"])
    assert crawler.next_index(tmp_path) == 21
    monkeypatch.setattr(crawler, "list_example_ids", lambda: [])
    assert crawler.next_index(tmp_path) == 1
