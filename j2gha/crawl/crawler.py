"""Crawl github.com for Jenkins pipelines of different styles and materialise scored examples.

Pipeline: code-search per style -> repo metadata + licence filter -> pin one commit snapshot -> blob fetch + de-dup ->
batch Groovy AST + analysis -> last-commit date for the file -> score -> coverage-driven selection ->
write examples/NNN/{Jenkinsfile,README.md,source.json}.

Discovery (the code-search index, a branch tree) only says where to look. Everything recorded - blob, text, file
history, citation URL - is read from a single commit the default branch pointed at when the candidate was examined
(``snapshot_commit``), so the pieces cannot disagree when the branch moves or a cached response is stale.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..analysis.analyze import STYLE_TITLES, analyse
from ..analysis.ast import AstUnavailable, dump_sources
from ..config import EXAMPLES_DIR, list_example_ids
from ..github import GitHub, GitHubError
from ..readme import render_example_readme
from .scoring import score_candidate
from .styles import PIPELINE_HINT_RE, SKIP_PATH_PARTS, STYLE_QUERIES, is_pipeline_path


def log(msg: str) -> None:
    print(f"[crawl] {msg}", file=sys.stderr, flush=True)


def _norm_hash(text: str) -> str:
    stripped = re.sub(r"//[^\n]*", "", text)
    stripped = re.sub(r"\s+", " ", stripped).strip().lower()
    return hashlib.sha256(stripped.encode()).hexdigest()


def existing_corpus(out_dir: Path) -> tuple[set[str], set[str], set[str], Counter]:
    repos, hashes, keys = set(), set(), set()
    styles: Counter = Counter()
    for ex_id in list_example_ids():
        meta_file = out_dir / ex_id / "source.json"
        if not meta_file.exists():
            continue
        meta = json.loads(meta_file.read_text())
        repos.add(meta["repository"]["full_name"].lower())
        keys.add(f"{meta['repository']['full_name'].lower()}::{meta['path']}")
        hashes.add(meta.get("content_hash", ""))
        styles.update(meta.get("styles", []))
    return repos, hashes, keys, styles


def search_candidates(gh: GitHub, styles: list[str], per_query: int, pages: int) -> dict[str, dict[str, Any]]:
    cands: dict[str, dict[str, Any]] = {}
    for style in styles:
        for q in STYLE_QUERIES[style]:
            for page in range(1, pages + 1):
                try:
                    res = gh.search_code(q, per_page=per_query, page=page)
                except GitHubError as e:
                    log(f"search failed for {q!r}: {e}")
                    break
                items = res.get("items", [])
                log(f"{style:<20} p{page} {len(items):>3} hits (total {res.get('total_count')}) :: {q}")
                for rank, it in enumerate(items):
                    full = it["repository"]["full_name"]
                    path = it["path"]
                    if any(part in f"/{path}" for part in SKIP_PATH_PARTS):
                        continue
                    key = f"{full.lower()}::{path}"
                    c = cands.setdefault(key, {"key": key, "full_name": full, "path": path, "sha": it["sha"],
                                               "html_url": it["html_url"], "found_by": [], "rank": 10_000})
                    if style not in c["found_by"]:
                        c["found_by"].append(style)
                    c["rank"] = min(c["rank"], (page - 1) * per_query + rank)
                if len(items) < per_query:
                    break
    return cands


def _search_shortlist(gh: GitHub, styles: list[str], per_query: int, pages: int, used_repos: set[str],
                      used_keys: set[str], limit: int) -> dict[str, dict[str, Any]]:
    cands = search_candidates(gh, styles, per_query, pages)
    log(f"{len(cands)} unique candidate files from search")
    # keep the best-ranked file per repo and drop repos already in the corpus
    best_per_repo: dict[str, dict[str, Any]] = {}
    for c in sorted(cands.values(), key=lambda c: (c["rank"], -len(c["found_by"]))):
        repo_key = c["full_name"].lower()
        if repo_key in used_repos or c["key"] in used_keys:
            continue
        if repo_key in best_per_repo:
            best_per_repo[repo_key]["found_by"] = sorted(set(best_per_repo[repo_key]["found_by"]) | set(c["found_by"]))
            continue
        best_per_repo[repo_key] = c
    pool = list(best_per_repo.values())
    # analyse a bounded, style-balanced subset
    by_style: dict[str, list[dict[str, Any]]] = {s: [] for s in styles}
    for c in sorted(pool, key=lambda c: c["rank"]):
        for s in c["found_by"]:
            by_style.setdefault(s, []).append(c)
    shortlist: dict[str, dict[str, Any]] = {}
    i = 0
    while len(shortlist) < min(limit, len(pool)):
        progressed = False
        for s in styles:
            lst = by_style.get(s, [])
            if i < len(lst):
                shortlist.setdefault(lst[i]["key"], lst[i])
                progressed = True
                if len(shortlist) >= limit:
                    break
        if not progressed:
            break
        i += 1
    log(f"shortlisted {len(shortlist)} candidates (one per repo) for metadata + analysis")
    return shortlist


def owner_candidates(gh: GitHub, owners: list[str]) -> dict[str, dict[str, Any]]:
    """Every pipeline-looking file on the default branch of each owner's non-fork repositories.

    Unlike code search this sees archived repositories and unconventional file names. Ranked by the repository's
    last push so that, among identical files, the most recently maintained copy is kept.
    """
    cands: dict[str, dict[str, Any]] = {}
    for owner in owners:
        try:
            repos = [r for r in gh.owner_repos(owner) if not r.get("fork")]
        except GitHubError as e:
            log(f"cannot list repositories of {owner}: {e.status}")
            continue
        repos.sort(key=lambda r: r.get("pushed_at") or "", reverse=True)
        hits = 0
        for repo in repos:
            full = repo["full_name"]
            try:
                tree = gh.tree(full, repo["default_branch"])
            except GitHubError as e:
                log(f"skip tree {full}: " + ("empty repository" if e.status == 409 else str(e.status)))
                continue
            if tree.get("truncated"):
                log(f"tree of {full} is truncated; some files may be missed")
            for node in tree.get("tree", []):
                path = node["path"]
                if node.get("type") != "blob" or not is_pipeline_path(path):
                    continue
                key = f"{full.lower()}::{path}"
                cands[key] = {"key": key, "full_name": full, "path": path, "sha": node["sha"],
                              "html_url": f"https://github.com/{full}/blob/{repo['default_branch']}/{path}",
                              "found_by": [f"owner:{owner}"], "rank": len(cands)}
                hits += 1
        log(f"owner {owner}: {len(repos)} non-fork repositories, {hits} pipeline-looking files")
    return cands


def resolve_head(gh: GitHub, full_name: str, branch: str) -> str:
    """The commit ``branch`` points at now. Never cached: a day-old head is exactly the drift being avoided."""
    ref = gh.get(f"/repos/{full_name}/git/ref/heads/{quote(branch, safe='/')}", use_cache=False)
    return ref["object"]["sha"]


def blob_at(gh: GitHub, full_name: str, commit: str, path: str) -> str | None:
    """SHA of the regular file at ``path`` in ``commit``; None when it is absent (or a symlink/submodule/directory).

    Keyed by an immutable commit SHA, so the GET cache is safe here.
    """
    try:
        node = gh.get(f"/repos/{full_name}/contents/{quote(path)}", params={"ref": commit})
    except GitHubError as e:
        if e.status == 404:
            return None
        raise
    if not isinstance(node, dict) or node.get("type") != "file":
        return None
    return node.get("sha")


def pin_snapshot(gh: GitHub, c: dict[str, Any], branch: str, heads: dict[str, str | None]) -> bool:
    """Anchor candidate ``c`` to one commit of ``branch`` (resolved once per repository per crawl).

    The discovered blob (search index, branch tree) may lag the branch. When it differs from the blob at the path in
    the snapshot, the snapshot's blob is used and its text is fetched instead: the file still exists, and analysis,
    history and the citation then all describe the same bytes. The stale SHA is kept as ``discovered_blob_sha``.
    Returns False (drop the candidate) when the snapshot cannot be read or no longer holds the file.
    """
    full = c["full_name"]
    repo_key = full.lower()
    if repo_key not in heads:
        try:
            heads[repo_key] = resolve_head(gh, full, branch)
        except (GitHubError, KeyError, TypeError) as e:
            log(f"skip {full}: cannot resolve {branch} to a commit ({getattr(e, 'status', e)})")
            heads[repo_key] = None
    commit = heads[repo_key]
    if commit is None:
        return False
    try:
        sha = blob_at(gh, full, commit, c["path"])
    except GitHubError as e:
        log(f"skip {c['key']}: cannot read it at {commit[:10]} ({e.status})")
        return False
    if sha is None:
        log(f"skip {c['key']}: no longer a file at {branch}@{commit[:10]}")
        return False
    if sha != c["sha"]:
        log(f"{c['key']}: discovered blob {c['sha'][:10]} is not the file at {branch}@{commit[:10]}; "
            f"using snapshot blob {sha[:10]}")
        c["discovered_blob_sha"] = c["sha"]
        c["sha"] = sha
    c["snapshot_commit"] = commit
    return True


def _drop_near_duplicates(cands: list[dict[str, Any]], seen: list[str], threshold: float = 0.9) -> list[dict[str, Any]]:
    """Organisations template their Jenkinsfiles; keep one of each family (input order wins)."""
    from difflib import SequenceMatcher

    def similar(a: str, b: str) -> bool:
        sm = SequenceMatcher(None, a, b, autojunk=False)
        return sm.real_quick_ratio() >= threshold and sm.quick_ratio() >= threshold and sm.ratio() >= threshold

    kept: list[dict[str, Any]] = []
    texts = list(seen)
    for c in cands:
        if any(similar(t, c["text"]) for t in texts):
            log(f"skip near-duplicate {c['key']}")
            continue
        kept.append(c)
        texts.append(c["text"])
    return kept


def _best_per_repo(ready: list[dict[str, Any]], covered: Counter, now: datetime) -> list[dict[str, Any]]:
    """One example per repository, as for search crawls: the file that scores highest against the pool."""
    freq = Counter(s for c in ready for s in c["analysis"]["styles"])
    pool_style_freq = {s: n / max(1, len(ready)) for s, n in freq.items()}
    best: dict[str, tuple[float, dict[str, Any]]] = {}
    for c in ready:
        total = score_candidate(c, pool_style_freq, set(covered), now)["total"]
        repo_key = c["full_name"].lower()
        if repo_key not in best or total > best[repo_key][0]:
            if repo_key in best:
                log(f"skip {best[repo_key][1]['key']}: {c['path']} scores higher in the same repository")
            best[repo_key] = (total, c)
        else:
            log(f"skip {c['key']}: {best[repo_key][1]['path']} scores higher in the same repository")
    return [c for _, c in best.values()]


def crawl(count: int, out_dir: Path = EXAMPLES_DIR, per_query: int = 30, pages: int = 1,
          max_analyse: int | None = None, allow_unlicensed: bool = False, styles: list[str] | None = None,
          dry_run: bool = False, verbose: bool = False, owners: list[str] | None = None) -> list[dict[str, Any]]:
    gh = GitHub(verbose=verbose)
    if not gh.token:
        raise SystemExit("GitHub code search needs authentication: set GH_TOKEN or run `gh auth login`.")
    now = datetime.now(timezone.utc)
    styles = styles or list(STYLE_QUERIES)
    check_capacity(count, out_dir)  # before any search: the batch must fit below the twin range
    used_repos, used_hashes, used_keys, covered = existing_corpus(out_dir)
    log(f"existing corpus: {len(used_keys)} examples; target +{count}")

    # 1. search -------------------------------------------------------------------------------
    if owners:
        # targeted: analyse every pipeline file of the owners; the best one per repo is chosen after scoring
        cands = owner_candidates(gh, owners)
        shortlist = {k: c for k, c in cands.items()
                     if c["full_name"].lower() not in used_repos and k not in used_keys}
        if max_analyse:
            shortlist = dict(list(shortlist.items())[:max_analyse])
        log(f"shortlisted {len(shortlist)} candidates for metadata + analysis")
    else:
        shortlist = _search_shortlist(gh, styles, per_query, pages, used_repos, used_keys,
                                      max_analyse or max(40, count * 8))

    # 2. metadata, licence filter, snapshot, content -----------------------------------------
    ready: list[dict[str, Any]] = []
    heads: dict[str, str | None] = {}  # repository -> the commit its default branch was pinned to
    for c in shortlist.values():
        try:
            repo = gh.repo(c["full_name"])
        except GitHubError as e:
            log(f"skip {c['full_name']}: {e.status}")
            continue
        lic = (repo.get("license") or {}).get("spdx_id")
        if not allow_unlicensed and lic in (None, "NOASSERTION"):
            continue
        if repo.get("private") or repo.get("disabled"):
            continue
        if not pin_snapshot(gh, c, repo["default_branch"], heads):
            continue
        try:
            text = gh.blob_text(c["full_name"], c["sha"])
        except GitHubError as e:
            log(f"skip blob {c['key']}: {e.status}")
            continue
        if len(text) < 200 or len(text) > 80_000:
            continue
        if owners and not PIPELINE_HINT_RE.search(text):
            continue
        h = _norm_hash(text)
        if h in used_hashes:
            continue
        used_hashes.add(h)
        c.update(repo=_repo_meta(repo), text=text, content_hash=h)
        ready.append(c)
    if owners:
        corpus_texts = [(out_dir / i / "Jenkinsfile").read_text() for i in list_example_ids()
                        if (out_dir / i / "Jenkinsfile").exists()]
        ready = _drop_near_duplicates(ready, corpus_texts)
    log(f"{len(ready)} candidates passed licence/size/duplicate filters")

    # 3. AST + analysis ------------------------------------------------------------------------
    try:
        asts = dump_sources({c["key"]: c["text"] for c in ready})
    except AstUnavailable as e:
        raise SystemExit(f"AST analysis unavailable: {e}") from e
    for c in ready:
        c["analysis"] = analyse(c["text"], asts[c["key"]])
    ready = [c for c in ready if c["analysis"]["dialect"] not in ("unknown",)]

    # 4. file history for the shortlist, as of the snapshot -------------------------------------
    for c in ready:
        try:
            commit = gh.last_commit_for_path(c["full_name"], c["path"], c["snapshot_commit"])
        except GitHubError:
            commit = None
        if commit:
            c["file_last_commit_sha"] = commit["sha"]
            c["file_last_commit_date"] = commit["commit"]["committer"]["date"]
        else:
            c["file_last_commit_sha"] = None
            c["file_last_commit_date"] = None
    if owners:
        ready = _best_per_repo(ready, covered, now)

    # 5. selection: coverage-driven round robin over styles ------------------------------------
    pool_freq = Counter(s for c in ready for s in c["analysis"]["styles"])
    pool_style_freq = {s: n / max(1, len(ready)) for s, n in pool_freq.items()}
    selected: list[dict[str, Any]] = []
    used_owners = {r.split("/")[0] for r in used_repos}
    covered_now = set(covered)
    remaining = list(ready)
    while len(selected) < count and remaining:
        # prefer styles least represented in the corpus so far
        order = sorted(styles, key=lambda s: (covered[s] + sum(1 for x in selected if s in x["analysis"]["styles"]),
                                              styles.index(s)))
        picked = None
        for s in order:
            options = [c for c in remaining if s in c["analysis"]["styles"]]
            if not options:
                continue
            # prefer owners not yet represented (avoid e.g. ten apache/* examples)
            taken = {x["full_name"].split("/")[0].lower() for x in selected} | used_owners
            fresh = [c for c in options if c["full_name"].split("/")[0].lower() not in taken]
            options = fresh or options
            scored = [(score_candidate(c, pool_style_freq, covered_now, now), c) for c in options]
            scored.sort(key=lambda sc: -sc[0]["total"])
            score, picked = scored[0]
            picked["score"] = score
            picked["primary_style"] = s
            break
        if picked is None:
            scored = [(score_candidate(c, pool_style_freq, covered_now, now), c) for c in remaining]
            scored.sort(key=lambda sc: -sc[0]["total"])
            picked = scored[0][1]
            picked["score"] = scored[0][0]
            picked["primary_style"] = picked["analysis"]["styles"][0] if picked["analysis"]["styles"] else "other"
        remaining.remove(picked)
        selected.append(picked)
        covered_now.update(picked["analysis"]["styles"])
        log(f"selected {picked['full_name']}:{picked['path']} [{picked['primary_style']}] score={picked['score']['total']}")

    if dry_run:
        return selected
    return write_examples(selected, out_dir, now)


def _repo_meta(repo: dict[str, Any]) -> dict[str, Any]:
    return {k: repo.get(k) for k in ("full_name", "html_url", "description", "stargazers_count", "forks_count",
                                     "pushed_at", "updated_at", "created_at", "archived", "default_branch",
                                     "language", "topics")} | {
        "license": (repo.get("license") or {}).get("spdx_id"),
        "license_name": (repo.get("license") or {}).get("name"),
    }


# crawled examples are 001-099; 1NN are the local twins of 0NN (.claude/skills/jenkins-example-twin)
MAX_CRAWLED_ID = 99


def next_index(out_dir: Path) -> int:
    ids = [int(x) for x in list_example_ids() if int(x) <= MAX_CRAWLED_ID]
    return (max(ids) + 1) if ids else 1


def check_capacity(count: int, out_dir: Path) -> int:
    """The first id for `count` new examples; refuses a batch that would reach the twin range (100+)."""
    first = next_index(out_dir)
    if count > 0 and first + count - 1 > MAX_CRAWLED_ID:
        free = max(0, MAX_CRAWLED_ID - first + 1)
        raise SystemExit(f"crawled examples are numbered up to {MAX_CRAWLED_ID:03d} (1NN are the twins of 0NN): "
                         f"{free} id(s) left, {count} requested")
    return first


def write_examples(selected: list[dict[str, Any]], out_dir: Path, now: datetime) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    idx = check_capacity(len(selected), out_dir)
    written = []
    for c in selected:
        ex_id = f"{idx:03d}"
        d = out_dir / ex_id
        d.mkdir(parents=True, exist_ok=False)
        (d / "Jenkinsfile").write_text(c["text"] if c["text"].endswith("\n") else c["text"] + "\n", encoding="utf-8")
        commit_sha = c.get("file_last_commit_sha")
        # the snapshot commit is the one known to hold blob_sha at this path
        ref = c.get("snapshot_commit") or commit_sha or c["repo"]["default_branch"]
        meta = {
            "id": ex_id,
            "retrieved_at": now.isoformat(timespec="seconds"),
            "repository": c["repo"],
            "path": c["path"],
            "blob_sha": c["sha"],
            "snapshot_commit": c.get("snapshot_commit"),
            **({"discovered_blob_sha": c["discovered_blob_sha"]} if c.get("discovered_blob_sha") else {}),
            "file_url": f"https://github.com/{c['full_name']}/blob/{ref}/{c['path']}",
            "file_last_commit_sha": commit_sha,
            "file_last_commit_date": c.get("file_last_commit_date"),
            "content_hash": c["content_hash"],
            "found_by_queries": c["found_by"],
            "primary_style": c["primary_style"],
            "styles": c["analysis"]["styles"],
            "dialect": c["analysis"]["dialect"],
            "score": c["score"],
            "crawl_analysis": {k: c["analysis"][k] for k in ("metrics", "complexity", "convertibility")},
        }
        (d / "source.json").write_text(json.dumps(meta, indent=2) + "\n")
        (d / "README.md").write_text(render_example_readme(meta, STYLE_TITLES))
        written.append(meta)
        log(f"wrote {d}")
        idx += 1
    return written


def rescore(out_dir: Path = EXAMPLES_DIR) -> None:
    """Recompute scores for existing examples (e.g. after changing the scoring model) and re-render READMEs."""
    from ..readme import update_header

    metas = []
    for ex_id in list_example_ids():
        f = out_dir / ex_id / "source.json"
        if f.exists():
            metas.append(json.loads(f.read_text()))
    texts = {m["id"]: (out_dir / m["id"] / "Jenkinsfile").read_text() for m in metas}
    asts = dump_sources(texts)
    analyses = {k: analyse(texts[k], asts[k]) for k in texts}
    freq = Counter(s for a in analyses.values() for s in a["styles"])
    pool_style_freq = {s: n / max(1, len(analyses)) for s, n in freq.items()}
    covered: set[str] = set()
    now = datetime.now(timezone.utc)
    for m in metas:
        cand = {"repo": m["repository"], "analysis": analyses[m["id"]], "text": texts[m["id"]],
                "file_last_commit_date": m.get("file_last_commit_date")}
        m["score"] = score_candidate(cand, pool_style_freq, covered, now)
        m["styles"] = analyses[m["id"]]["styles"]
        covered.update(m["styles"])
        (out_dir / m["id"] / "source.json").write_text(json.dumps(m, indent=2) + "\n")
        update_header(out_dir / m["id"] / "README.md", m, STYLE_TITLES)
        log(f"{m['id']}: {m['score']['total']}")

