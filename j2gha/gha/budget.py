"""GitHub Actions minutes monitoring and the hosted-run budget guard.

The guard decides against the billing owner of the *target* repository (J2GHA_REPO / the origin remote):
  - public repository: standard GitHub-hosted runners are free, so only the per-run cap applies
  - private repository: the owner's usage this month, best source first:
      1. Enhanced billing API usage summary (?year&month&product=actions)
           user-owned  GET /users/{user}/settings/billing/usage/summary
           org-owned   GET /organizations/{org}/settings/billing/usage/summary
      2. Fallback tally: billable minutes from the jobs API for this month's runs in the owner's private
         repositories the token can list (each job rounded up to a whole minute, OS multipliers applied). It cannot
         see other repositories or products, so it is a lower bound: usage is marked incomplete and the guard refuses
         it unless J2GHA_ALLOW_INCOMPLETE_USAGE=1.
Approved worst-case minutes are reserved in the ledger before dispatch and reconciled with the run's billable minutes
afterwards; unreconciled reservations of the month count as used. Ledger read-modify-writes are serialised with flock.
The legacy /settings/billing/actions endpoint was retired in 2025; the per-run /timing endpoint now reports 0.
"""

from __future__ import annotations

import fcntl
import json
import math
import os
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import requests

from ..config import STATE_DIR
from ..github import GitHub, GitHubError

INCLUDED_DEFAULT = int(os.environ.get("J2GHA_INCLUDED_MINUTES", "2000"))  # Free plan; Pro = 3000
RESERVE_PCT = float(os.environ.get("J2GHA_RESERVE_PCT", "20"))  # keep this share of the allowance untouched
MAX_RUN_MINUTES = int(os.environ.get("J2GHA_MAX_RUN_MINUTES", "30"))  # worst-case ceiling for a single run
STALE_HOURS = 24  # pending reservations older than this are flagged by `j2gha budget` (they count until cleared)
PLAN_MINUTES = {"free": 2000, "pro": 3000, "team": 3000, "enterprise": 50000}
MULTIPLIER = {"linux": 1, "windows": 2, "macos": 10}
LEDGER = STATE_DIR / "usage-ledger.jsonl"  # one reservation per line; status pending|reconciled|released|cleared
RUN_CACHE = STATE_DIR / "run-minutes-cache.json"
ACTIVE_DIR = STATE_DIR / "remote-runs"  # gha.remote's in-flight run state; files left behind = abnormal exits
BILLING_HELP = ("for billing data use a classic token with the `user` scope (gh auth refresh -h github.com -s user) or "
                "a fine-grained token with Plan: read; an organisation needs an owner/billing manager token "
                "(fine-grained: Administration: read)")


def log(msg: str) -> None:
    print(f"[budget] {msg}", file=sys.stderr, flush=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mult(labels: list[str]) -> int:
    text = " ".join(labels).lower()
    if "self-hosted" in text:
        return 0
    if "macos" in text:
        return MULTIPLIER["macos"]
    if "windows" in text:
        return MULTIPLIER["windows"]
    return 1


def job_billable_minutes(job: dict[str, Any]) -> int:
    started, completed = job.get("started_at"), job.get("completed_at")
    if not started or not completed:
        return 0
    s = datetime.fromisoformat(started.replace("Z", "+00:00"))
    c = datetime.fromisoformat(completed.replace("Z", "+00:00"))
    secs = max(0.0, (c - s).total_seconds())
    if secs == 0:
        return 0
    return math.ceil(secs / 60) * _mult(job.get("labels", []))


def run_billable_minutes(gh: GitHub, repo: str, run_id: int) -> int:
    total = 0
    page = 1
    while True:
        data = gh.get(f"/repos/{repo}/actions/runs/{run_id}/jobs", params={"filter": "all", "per_page": 100, "page": page},
                      use_cache=False)
        for job in data.get("jobs", []):
            total += job_billable_minutes(job)
        if len(data.get("jobs", [])) < 100:
            break
        page += 1
    return total


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _load_cache() -> dict[str, int]:
    return _read_json(RUN_CACHE)


def tally_month(gh: GitHub, repos: list[str], refresh: bool = False) -> dict[str, Any]:
    """Lower-bound tally; a repository whose runs cannot be listed is reported in `errors`, never counted as 0."""
    since = _now().strftime("%Y-%m-01")
    cache = {} if refresh else _load_cache()
    per_repo: dict[str, int] = {}
    errors: list[str] = []
    for repo in repos:
        minutes = 0
        page = 1
        try:
            while True:
                data = gh.get(f"/repos/{repo}/actions/runs", params={"created": f">={since}", "per_page": 100,
                                                                    "page": page}, use_cache=False)
                runs = data.get("workflow_runs", [])
                for run in runs:
                    key = f"{repo}#{run['id']}#{run.get('run_attempt', 1)}"
                    if key in cache and run.get("status") == "completed":
                        minutes += cache[key]
                        continue
                    m = run_billable_minutes(gh, repo, run["id"])
                    if run.get("status") == "completed":
                        cache[key] = m
                    minutes += m
                if len(runs) < 100:
                    break
                page += 1
        except GitHubError as e:
            log(f"{repo}: {e.status}")
            errors.append(f"{repo}: listing runs failed ({e.status}) after {minutes} min")
        if minutes:
            per_repo[repo] = minutes
    RUN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    RUN_CACHE.write_text(json.dumps(cache))
    return {"used": sum(per_repo.values()), "per_repo": per_repo, "errors": errors}


def billing_summary(gh: GitHub, owner: str, org: bool = False) -> dict[str, Any]:
    """Actions minutes from the usage summary; raises GitHubError when unavailable, ValueError on an unknown shape."""
    now = _now()
    base = f"/organizations/{owner}" if org else f"/users/{owner}"
    data = gh.get(f"{base}/settings/billing/usage/summary",
                  params={"year": now.year, "month": now.month, "product": "actions"}, use_cache=False)
    items = data.get("usageItems") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("unexpected billing usage summary response (no usageItems list)")
    used = 0.0
    net = 0.0
    skus: dict[str, float] = {}
    for item in items:
        if "minute" not in str(item.get("unitType", "")).lower():
            continue
        sku = str(item.get("sku", "")).lower()
        mult = MULTIPLIER["macos"] if "macos" in sku else (MULTIPLIER["windows"] if "windows" in sku else 1)
        qty = float(item.get("grossQuantity") or item.get("quantity") or 0)
        used += qty * mult
        net += float(item.get("netAmount") or 0)
        skus[sku] = skus.get(sku, 0) + qty
    return {"used": round(used), "net_amount_usd": round(net, 2), "skus": skus}


def whoami(gh: GitHub) -> dict[str, Any]:
    """Authenticated login, plan and classic OAuth scopes (fine-grained tokens send no X-OAuth-Scopes header)."""
    try:
        r = gh.request("GET", "/user", raw=True, use_cache=False)
        data = r.json()
    except GitHubError:
        return {"login": None, "plan": None, "scopes": []}
    return {"login": data.get("login"), "plan": (data.get("plan") or {}).get("name"),
            "scopes": [s.strip() for s in r.headers.get("X-OAuth-Scopes", "").split(",") if s.strip()]}


def target_account(gh: GitHub, repo: str) -> dict[str, Any]:
    """Billing owner of the repository the harness dispatches to; a missing `private` flag counts as private."""
    data = gh.get(f"/repos/{repo}", use_cache=False)
    owner = data.get("owner") or {}
    if not owner.get("login"):
        raise RuntimeError(f"no owner in the /repos/{repo} response")
    return {"repo": repo, "owner": owner["login"], "owner_type": owner.get("type") or "User",
            "private": data.get("private") is not False}


def default_repo() -> str:
    from .remote import harness_repo  # deferred: remote imports this module

    return harness_repo()


def _private_repos(gh: GitHub, account: dict[str, Any], me: str | None) -> tuple[list[str], list[str]]:
    """Repositories the fallback tally can see for the owner, plus the gaps it knows about."""
    owner, own = account["owner"], [r for r in [account.get("repo")] if r]
    if account["owner_type"] == "Organization":
        path, params = f"/orgs/{owner}/repos", {"type": "private"}
    elif owner == me:
        path, params = "/user/repos", {"affiliation": "owner", "visibility": "private"}
    else:
        return own, [f"cannot list {owner}'s private repositories with this token"]
    repos: list[str] = []
    page = 1
    try:
        while True:
            data = gh.get(path, params={**params, "per_page": 100, "page": page}, use_cache=False)
            repos += [r["full_name"] for r in data]
            if len(data) < 100:
                return repos, []
            page += 1
    except GitHubError as e:
        return sorted(set(repos) | set(own)), [f"listing {owner}'s private repositories failed ({e.status})"]


def _plan(gh: GitHub, account: dict[str, Any], who: dict[str, Any]) -> str | None:
    if account["owner_type"] == "Organization":
        try:
            return ((gh.get(f"/orgs/{account['owner']}", use_cache=False) or {}).get("plan") or {}).get("name")
        except GitHubError:
            return None
    return who["plan"] if account["owner"] == who["login"] else None


def account_usage(gh: GitHub, account: dict[str, Any], who: dict[str, Any], refresh: bool = False) -> dict[str, Any]:
    """This month's usage of the account; `complete` is True only for billing API data."""
    owner, org = account["owner"], account["owner_type"] == "Organization"
    plan = _plan(gh, account, who)
    included = int(os.environ.get("J2GHA_INCLUDED_MINUTES") or PLAN_MINUTES.get(str(plan).lower(), INCLUDED_DEFAULT))
    base = {"owner": owner, "owner_type": account["owner_type"], "repo": account.get("repo"), "user": who["login"],
            "plan": plan, "included": included, "scopes": who["scopes"]}
    try:
        return {**base, **billing_summary(gh, owner, org=org), "complete": True,
                "source": f"billing-api ({'organization' if org else 'user'} usage summary)"}
    except (GitHubError, ValueError) as e:
        err = str(e.status) if isinstance(e, GitHubError) else str(e)
        log(f"billing API unavailable for {owner} ({err}); falling back to the jobs-API tally")
    repos, gaps = _private_repos(gh, account, who["login"])
    tally = tally_month(gh, repos, refresh=refresh)
    return {**base, "used": tally["used"], "per_repo": tally["per_repo"], "complete": False, "billing_error": err,
            "tally_errors": gaps + tally["errors"],
            "source": f"jobs-API tally of {owner}'s private repos (lower bound; {BILLING_HELP})"}


# ------------------------------------------------------------------------------------------- ledger
@contextmanager
def _ledger_lock() -> Iterator[None]:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.with_suffix(".lock").open("a") as f:  # a separate lock file: the ledger itself is replaced on write
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def read_ledger() -> list[dict[str, Any]]:
    try:
        lines = LEDGER.read_text().splitlines()
    except FileNotFoundError:
        return []
    entries = []
    for line in filter(str.strip, lines):
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            log(f"skipping a corrupt ledger line: {line[:80]}")
    return entries


def _update_ledger(fn: Callable[[list[dict[str, Any]]], Any]) -> Any:
    """Locked read-modify-write; `fn` edits the entry list in place. The file is replaced atomically."""
    with _ledger_lock():
        entries = read_ledger()
        result = fn(entries)
        tmp = LEDGER.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(e) + "\n" for e in entries))
        os.replace(tmp, LEDGER)
        return result


def _pending(entries: list[dict[str, Any]], owner: str | None) -> list[dict[str, Any]]:
    month = _now().strftime("%Y-%m")
    return [e for e in entries if e.get("status") == "pending" and str(e.get("at", "")).startswith(month)
            and (owner is None or e.get("owner") in (None, owner))]


def _pending_minutes(entries: list[dict[str, Any]], owner: str | None) -> int:
    return sum(int(e.get("reserved_minutes") or 0) for e in _pending(entries, owner))


def reserve(decision: dict[str, Any], **entry: Any) -> dict[str, Any] | None:
    """Reserve the approved worst case before dispatch. Re-checks the allowance under the lock, so it returns None
    when reservations made since `guard` left too little."""
    owner = (decision.get("account") or {}).get("owner")
    free = bool(decision.get("free_minutes"))
    worst = 0 if free else int(decision["estimate"]["worst_case"])

    def add(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
        if decision.get("available_after_reserve") is not None:
            taken = _pending_minutes(entries, owner) - int(decision.get("pending_minutes") or 0)
            if worst > decision["available_after_reserve"] - taken:
                return None
        e = {"id": uuid.uuid4().hex[:12], "status": "pending", "at": _now().isoformat(timespec="seconds"),
             "owner": owner, "free": free, "reserved_minutes": worst, "run_id": None, **entry}
        entries.append(e)
        return e

    e = _update_ledger(add)
    log(f"reserved {worst} min ({e['id']})" if e else f"cannot reserve {worst} min: taken by concurrent reservations")
    return e


def update_reservation(rid: str, **fields: Any) -> None:
    def upd(entries: list[dict[str, Any]]) -> None:
        for e in entries:
            if e.get("id") == rid:
                e.update(fields)

    _update_ledger(upd)


def settle(rid: str, billable: int, **fields: Any) -> None:
    update_reservation(rid, status="reconciled", billable_minutes=billable,
                       reconciled_at=_now().isoformat(timespec="seconds"), **fields)


def release(rid: str, why: str) -> None:
    """Drop a reservation whose run was never dispatched."""
    update_reservation(rid, status="released", reconciled_at=_now().isoformat(timespec="seconds"), note=why)


def clear_reservations(ids: list[str]) -> int:
    """Manually clear pending reservations (after checking their runs by hand); returns how many were cleared."""
    def clear(entries: list[dict[str, Any]]) -> int:
        hit = [e for e in entries if e.get("id") in ids and e.get("status") == "pending"]
        for e in hit:
            e.update(status="cleared", reconciled_at=_now().isoformat(timespec="seconds"))
        return len(hit)

    return _update_ledger(clear)


def reconcile(gh: GitHub) -> int:
    """Settle pending reservations whose run has completed, finding the run by head sha when its id is unknown."""
    updates: dict[str, dict[str, Any]] = {}
    for e in read_ledger():
        if e.get("status") != "pending" or not e.get("repo"):
            continue
        repo, run_id = e["repo"], e.get("run_id")
        try:
            if not run_id and e.get("sha"):
                runs = gh.get(f"/repos/{repo}/actions/runs", params={"head_sha": e["sha"], "per_page": 5},
                              use_cache=False)
                run_id = next((r["id"] for r in runs.get("workflow_runs", []) if r.get("head_sha") == e["sha"]), None)
                if run_id:
                    updates[e["id"]] = {"run_id": run_id}
            if not run_id:
                continue
            run = gh.get(f"/repos/{repo}/actions/runs/{run_id}", use_cache=False)
            if run.get("status") == "completed":
                updates[e["id"]] = {"run_id": run_id, "status": "reconciled", "result": run.get("conclusion"),
                                    "billable_minutes": run_billable_minutes(gh, repo, run_id),
                                    "reconciled_at": _now().isoformat(timespec="seconds")}
        except (GitHubError, requests.RequestException) as ex:
            log(f"cannot reconcile reservation {e['id']}: {ex}")
    if updates:
        def apply(entries: list[dict[str, Any]]) -> None:
            for e in entries:
                if e.get("id") in updates and e.get("status") == "pending":
                    e.update(updates[e["id"]])

        _update_ledger(apply)
        log(f"reconciled {sum(1 for u in updates.values() if u.get('status'))} reservation(s)")
    return len(updates)


def _stale(pending: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cutoff = _now() - timedelta(hours=STALE_HOURS)
    return [e for e in pending if datetime.fromisoformat(str(e["at"]).replace("Z", "+00:00")) < cutoff]


# ------------------------------------------------------------------------------------------- guard
def guard(estimate: dict[str, Any], yes: bool = False, max_minutes: int | None = None,
          repo: str | None = None) -> dict[str, Any]:
    gh = GitHub(cache_ttl=0)
    cap = max_minutes or MAX_RUN_MINUTES
    worst = estimate["worst_case"]
    reasons: list[str] = []
    if estimate.get("unbounded"):
        reasons.append("the worst case cannot be bounded (a matrix that cannot be expanded statically)")
    if worst > cap:
        reasons.append(f"worst case {worst} min exceeds the per-run cap of {cap} min "
                       "(--max-minutes / J2GHA_MAX_RUN_MINUTES)")
    decision: dict[str, Any] = {"allowed": False, "reasons": reasons, "estimate": estimate, "cap": cap,
                                "account": None, "usage": {}, "free_minutes": False, "usage_complete": None,
                                "pending_minutes": 0, "available_after_reserve": None}
    try:
        account = decision["account"] = target_account(gh, repo or default_repo())
    except (GitHubError, RuntimeError) as e:
        account = None
        reasons.append(f"cannot determine the billing owner of the target repository: {e}")
    if account and not account["private"]:
        decision["free_minutes"] = True
        decision["usage"] = {"owner": account["owner"], "used": None, "included": None,
                             "source": "not needed: public repository (standard GitHub-hosted runners are free)"}
    elif account:
        reconcile(gh)
        usage = account_usage(gh, account, whoami(gh))
        pending = _pending_minutes(read_ledger(), account["owner"])
        remaining = usage["included"] - usage["used"] - pending
        available = remaining - usage["included"] * RESERVE_PCT / 100
        decision.update(usage=usage, usage_complete=usage["complete"], pending_minutes=pending,
                        available_after_reserve=math.floor(available))
        if not usage["complete"]:
            if os.environ.get("J2GHA_ALLOW_INCOMPLETE_USAGE") == "1":
                decision["incomplete_usage_accepted"] = True
                log(f"WARNING: deciding on incomplete usage ({usage['source']}) - J2GHA_ALLOW_INCOMPLETE_USAGE=1")
            else:
                reasons.append(f"usage of {account['owner']} is incomplete ({usage['source']}); "
                               "set J2GHA_ALLOW_INCOMPLETE_USAGE=1 to decide on this lower bound")
        if usage.get("net_amount_usd", 0) > 0:
            reasons.append(f"paid usage already incurred this month (${usage['net_amount_usd']})")
        if worst > available:
            reasons.append(f"worst case {worst} min exceeds available {available:.0f} min (remaining {remaining:.0f} "
                           f"after {pending} min of pending reservations, minus {RESERVE_PCT:.0f}% reserve)")
    usage = decision["usage"]
    status = ("public repository: free" if decision["free_minutes"] else
              f"{usage.get('used')}/{usage.get('included')} used this month, {decision['pending_minutes']} reserved")
    decision["allowed"] = not reasons
    if decision["allowed"] and not yes:
        if sys.stdin.isatty():
            ans = input(f"Spend ~{estimate['typical']} (worst case {worst}) GitHub-hosted minutes? [{status}] y/N: ")
            decision["allowed"] = ans.strip().lower() in ("y", "yes")
            if not decision["allowed"]:
                reasons.append("declined at prompt")
        else:
            decision["allowed"] = False
            reasons.append("non-interactive: pass --yes to spend hosted minutes")
    log(("ALLOW" if decision["allowed"] else "REFUSE") + f": estimate {estimate}, {status}"
        + (f" - {'; '.join(reasons)}" if reasons else ""))
    return decision


# ------------------------------------------------------------------------------------------- report
def report(refresh: bool = False) -> dict[str, Any]:
    gh = GitHub(cache_ttl=0)
    who = whoami(gh)
    notes = []
    try:
        account = target_account(gh, default_repo())
    except (GitHubError, RuntimeError) as e:
        account = {"repo": None, "owner": who["login"], "owner_type": "User", "private": True}
        notes.append(f"  target repository unknown ({e}); showing the authenticated account")
    reconcile(gh)
    u = account_usage(gh, account, who, refresh=refresh)
    entries = read_ledger()
    month = _now().strftime("%Y-%m")
    done = [e for e in entries if str(e.get("at", "")).startswith(month)
            and e.get("status", "reconciled") == "reconciled" and not e.get("free")]  # legacy lines have no status
    harness = sum(int(e.get("billable_minutes") or 0) for e in done)
    pending = _pending(entries, u["owner"])
    pending_min = sum(int(e.get("reserved_minutes") or 0) for e in pending)
    stale = _stale(pending)
    reserve = u["included"] * RESERVE_PCT / 100
    remaining = u["included"] - u["used"] - pending_min
    pct = 100 * u["used"] / u["included"] if u["included"] else 0
    bar_len = 30
    filled = min(bar_len, int(round(bar_len * pct / 100)))
    visibility = "private" if account["private"] else "public: hosted minutes are free, only the per-run cap applies"
    lines = [f"GitHub Actions minutes for {u['owner']} ({u['owner_type'].lower()}) ({_now():%B %Y})",
             f"  target repository: {account['repo']} ({visibility})" if account.get("repo") else
             "  target repository: unknown", *notes,
             f"  [{'#' * filled}{'.' * (bar_len - filled)}] {u['used']} / {u['included']} min used ({pct:.1f}%)",
             "  usage data: " + ("complete" if u["complete"] else
                                 "INCOMPLETE (lower bound) - the hosted guard refuses it unless "
                                 "J2GHA_ALLOW_INCOMPLETE_USAGE=1"),
             f"  remaining: {remaining} min after {pending_min} min of pending reservations; guard keeps "
             f"{RESERVE_PCT:.0f}% in reserve -> {remaining - reserve:.0f} min available to the harness",
             f"  harness hosted runs this month: {len(done)} reconciled run(s), {harness} billable min (local ledger)"]
    if pending:
        lines.append(f"  pending reservations: {len(pending)}, {pending_min} min - " + ", ".join(
            f"{e['id']} {e.get('example')}/{e.get('mode')} run {e.get('run_id') or '?'} "
            f"{e.get('reserved_minutes')} min" for e in pending))
    if stale:
        what = [f"{e['id']} (run {e['run_id']} not reconciled)" if e.get("run_id") else
                f"{e['id']} (no run id, sha {str(e.get('sha'))[:7]})" for e in stale]
        lines.append(f"  WARNING: {len(stale)} reservation(s) older than {STALE_HOURS}h still count "
                     f"({sum(int(e.get('reserved_minutes') or 0) for e in stale)} min): {', '.join(what)}. "
                     f"Check the runs in {account.get('repo') or 'the repository'}'s Actions tab, then clear them "
                     f"(budget.clear_reservations, or \"status\": \"cleared\" in {LEDGER})")
    leftovers = [_read_json(p) for p in sorted(ACTIVE_DIR.glob("*.json"))] if ACTIVE_DIR.is_dir() else []
    if leftovers:
        lines.append(f"  remote runs in flight or left by abnormal exits ({ACTIVE_DIR}): " + ", ".join(
            f"{s.get('branch')} run {s.get('run_id') or '?'} {s.get('state')}" for s in leftovers))
    lines.append(f"  source: {u['source']}")
    if u.get("tally_errors"):
        lines.append("  tally gaps: " + "; ".join(u["tally_errors"]))
    if u.get("per_repo"):
        lines.append("  by repository: " + ", ".join(f"{k} {v}" for k, v in sorted(u["per_repo"].items(), key=lambda kv: -kv[1])))
    if u.get("skus"):
        lines.append("  by SKU: " + ", ".join(f"{k} {v:g}" for k, v in u["skus"].items()))
    return {**u, "account": account, "remaining": remaining, "pending_minutes": pending_min, "pending": pending,
            "stale": [e["id"] for e in stale], "harness_runs": len(done), "harness_minutes": harness,
            "text": "\n".join(lines)}
