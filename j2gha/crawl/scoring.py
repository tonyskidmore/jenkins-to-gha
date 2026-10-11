"""Example scoring (0-10) for crawled Jenkins pipelines.

Six criteria, weights sum to 10:

| criterion        | max | basis                                                                  |
|------------------|-----|------------------------------------------------------------------------|
| repo_activity    | 1.5 | age of the repository's last push (archived repos halved)              |
| file_freshness   | 1.5 | age of the last commit touching the Jenkinsfile                        |
| complexity       | 2.0 | structural richness: stages, distinct steps, styles, migration score   |
| value            | 2.0 | rarity of its styles in the candidate pool, novelty vs. corpus, showcase constructs |
| popularity       | 1.5 | GitHub stars on a log scale (10k+ stars = full marks)                  |
| quality          | 1.5 | parses cleanly, timeouts/post handling, no literal secrets, few unknown steps |
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from .styles import SHOWCASE_STYLES

MAX = {"repo_activity": 1.5, "file_freshness": 1.5, "complexity": 2.0, "value": 2.0, "popularity": 1.5,
       "quality": 1.5}

SECRET_RE = re.compile(r"(?i)\b(password|passwd|secret|token|apikey|api_key)\s*[:=]\s*['\"][^'\"$]{6,}['\"]")


def _age_days(iso: str | None, now: datetime) -> float | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (now - dt).total_seconds() / 86400)


def _age_points(days: float | None, bands: list[tuple[float, float]], floor: float) -> float:
    if days is None:
        return floor
    for limit, pts in bands:
        if days <= limit:
            return pts
    return floor


def score_candidate(cand: dict[str, Any], pool_style_freq: dict[str, float], covered_styles: set[str],
                    now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    repo = cand["repo"]
    analysis = cand["analysis"]
    m = analysis.get("metrics", {})
    styles = analysis.get("styles", [])
    parts: dict[str, dict[str, Any]] = {}

    # repo activity
    days = _age_days(repo.get("pushed_at"), now)
    pts = _age_points(days, [(90, 1.5), (365, 1.2), (730, 0.9), (1460, 0.5)], 0.2)
    if repo.get("archived"):
        pts *= 0.5
    parts["repo_activity"] = {"points": pts, "basis": f"last push {repo.get('pushed_at', '?')[:10]}"
                              + (" (archived)" if repo.get("archived") else "")}

    # file freshness
    fdays = _age_days(cand.get("file_last_commit_date"), now)
    pts = _age_points(fdays, [(180, 1.5), (365, 1.2), (730, 0.9), (1460, 0.6), (2190, 0.3)], 0.1)
    parts["file_freshness"] = {"points": pts, "basis": f"Jenkinsfile last changed {str(cand.get('file_last_commit_date') or '?')[:10]}"}

    # complexity / richness
    cscore = analysis.get("complexity", {}).get("score", 0)
    richness = (min(1, m.get("distinct_steps", 0) / 12) * 0.35 + min(1, m.get("stages", 0) / 8) * 0.25 +
                min(1, len(styles) / 6) * 0.25 + min(1, cscore / 60) * 0.15)
    parts["complexity"] = {"points": 2.0 * richness,
                           "basis": f"{m.get('stages', 0)} stages, {m.get('distinct_steps', 0)} distinct steps, "
                                    f"{len(styles)} styles, migration difficulty {cscore}/100"}

    # value / uniqueness
    rarity = sum(1 - pool_style_freq.get(s, 0) for s in styles) / len(styles) if styles else 0
    novel = [s for s in styles if s not in covered_styles]
    novelty = min(1.0, len(novel) / 3)
    showcase = sorted(set(styles) & SHOWCASE_STYLES)
    value = 0.8 * rarity + 0.7 * novelty + (0.5 if showcase else 0)
    basis = f"style rarity {rarity:.2f}"
    if novel:
        basis += f"; new to corpus: {', '.join(novel)}"
    if showcase:
        basis += f"; showcase: {', '.join(showcase)}"
    parts["value"] = {"points": value, "basis": basis}

    # popularity
    stars = int(repo.get("stargazers_count") or 0)
    parts["popularity"] = {"points": 1.5 * min(1.0, math.log10(stars + 1) / 4), "basis": f"{stars:,} stars"}

    # quality
    q = 1.0
    notes = []
    text = cand.get("text", "")
    if not analysis.get("parser", {}).get("ok"):
        q = 0.0
        notes.append("does not parse")
    else:
        if m.get("options") and "timeout" in text:
            q += 0.15
            notes.append("timeouts")
        if m.get("post_conditions") or "finally" in text:
            q += 0.15
            notes.append("post/cleanup handling")
        comment_lines = sum(1 for line in text.splitlines() if line.strip().startswith(("//", "/*", "*")))
        if comment_lines >= 2:
            q += 0.1
            notes.append("commented")
        if any(c.get("type") == "credentials()" or c.get("type") for c in analysis.get("credentials", [])):
            q += 0.1
            notes.append("uses credential bindings")
        if SECRET_RE.search(text):
            q -= 0.6
            notes.append("possible literal secret")
        unknown = m.get("unknown_steps", 0)
        if unknown > 3:
            q -= 0.2
            notes.append(f"{unknown} unmapped custom steps")
        if analysis.get("jenkins_model", {}).get("result") == "failure":
            q -= 0.7
            notes.append("fails Jenkins validation")
        if m.get("loc", 0) < 15:
            q -= 0.2
            notes.append("very small")
    parts["quality"] = {"points": max(0.0, min(1.5, q)), "basis": ", ".join(notes) or "baseline"}

    for k, v in parts.items():
        v["points"] = round(min(MAX[k], max(0.0, v["points"])), 2)
        v["max"] = MAX[k]
    total = round(sum(v["points"] for v in parts.values()), 1)
    return {"total": total, "parts": parts, "summary": summarise(total, parts, analysis)}


def summarise(total: float, parts: dict[str, dict[str, Any]], analysis: dict[str, Any]) -> str:
    ratio = {k: v["points"] / v["max"] for k, v in parts.items()}
    labels = {"repo_activity": "an actively maintained repository", "file_freshness": "a recently updated Jenkinsfile",
              "complexity": "a structurally rich pipeline", "value": "styles that are rare/new for the corpus",
              "popularity": "a popular repository", "quality": "good pipeline hygiene"}
    weak = {"repo_activity": "the repository is stale", "file_freshness": "the Jenkinsfile has not changed in years",
            "complexity": "the pipeline is simple", "value": "its styles are already common in the corpus",
            "popularity": "the repository has few stars", "quality": "quality issues"}
    strengths = [labels[k] for k, r in sorted(ratio.items(), key=lambda kv: -kv[1]) if r >= 0.7][:3]
    weaknesses = [weak[k] for k, r in sorted(ratio.items(), key=lambda kv: kv[1]) if r < 0.4][:2]
    style_txt = ", ".join(analysis.get("styles", [])[:5]) or "unclassified"
    s = f"Scored {total}/10 as a {analysis.get('dialect', '?')} pipeline ({style_txt})"
    if strengths:
        s += "; strengths: " + ", ".join(strengths)
    if weaknesses:
        s += "; held back because " + " and ".join(weaknesses)
    q = parts["quality"]["basis"]
    if "secret" in q or "fails" in q or "parse" in q:
        s += f" (quality: {q})"
    return s + "."
