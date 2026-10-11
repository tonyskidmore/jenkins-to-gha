"""Hosted-minutes guard: billing owner, completeness, reservations. Every GitHub call is faked; nothing leaves the box."""

import json
import re
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import requests

from j2gha.gha import budget
from j2gha.github import GitHubError

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
EST = {"typical": 6, "worst_case": 30}


class FakeGH:
    """Routes {(METHOD, path regex): value | exception | callable(params)}; every call is recorded."""

    routes: dict = {}
    calls: list = []

    def __init__(self, *a, **k):
        pass

    def request(self, method, path, params=None, raw=False, **k):
        FakeGH.calls.append((method, path, dict(params or {})))
        for (m, pattern), v in FakeGH.routes.items():
            if m == method and re.fullmatch(pattern, path):
                if isinstance(v, Exception):
                    raise v
                return v(params or {}) if callable(v) else v
        raise AssertionError(f"unexpected {method} {path}")

    def get(self, path, **k):
        return self.request("GET", path, **k)


def user(login="me", scopes="repo, workflow", plan="free"):
    headers = {} if scopes is None else {"X-OAuth-Scopes": scopes}
    return SimpleNamespace(headers=headers, json=lambda: {"login": login, "plan": {"name": plan}})


def repo(owner="me", kind="User", private=True):
    return {"owner": {"login": owner, "type": kind}, "private": private}


def summary(minutes, net=0):
    return {"usageItems": [{"product": "actions", "sku": "actions_linux", "unitType": "Minutes",
                            "grossQuantity": minutes, "netAmount": net},
                           {"product": "actions", "sku": "actions_storage", "unitType": "GigabyteHours",
                            "grossQuantity": 5}]}


def denied(status=403):
    return GitHubError(status, "Resource not accessible by integration", "x")


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    def no_http(*a, **k):
        raise AssertionError(f"real HTTP call attempted: {a[1:3]}")

    monkeypatch.setattr(requests.Session, "request", no_http)
    for var in ("GH_TOKEN", "GITHUB_TOKEN", "J2GHA_ALLOW_INCOMPLETE_USAGE", "J2GHA_INCLUDED_MINUTES"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("J2GHA_REPO", "me/harness")
    monkeypatch.setattr(budget, "GitHub", FakeGH)
    monkeypatch.setattr(budget, "_now", lambda: NOW)
    monkeypatch.setattr(budget, "LEDGER", tmp_path / "usage-ledger.jsonl")
    monkeypatch.setattr(budget, "RUN_CACHE", tmp_path / "run-minutes-cache.json")
    monkeypatch.setattr(budget, "ACTIVE_DIR", tmp_path / "remote-runs")
    FakeGH.routes, FakeGH.calls = {}, []


def route(extra=None):
    """Base routes for the user-owned private repo `me/harness` (100 min used), plus `extra`."""
    FakeGH.routes = {("GET", "/user"): user(), ("GET", "/repos/me/harness"): repo(),
                     ("GET", "/users/me/settings/billing/usage/summary"): summary(100), **(extra or {})}


def called(pattern):
    return [c for c in FakeGH.calls if re.search(pattern, c[1])]


def write_ledger(*entries):
    budget.LEDGER.write_text("".join(json.dumps(e) + "\n" for e in entries))


def test_lower_bound_usage_is_refused_unless_overridden(monkeypatch):
    route({("GET", "/users/me/settings/billing/usage/summary"): denied(),
           ("GET", "/user/repos"): [{"full_name": "me/harness"}],
           ("GET", "/repos/me/harness/actions/runs"): {"workflow_runs": []}})
    d = budget.guard(EST, yes=True)
    assert not d["allowed"] and d["usage"]["complete"] is False and d["usage_complete"] is False
    assert d["usage"]["used"] == 0 and d["usage"]["billing_error"] == "403"
    assert any("incomplete" in r and "J2GHA_ALLOW_INCOMPLETE_USAGE=1" in r for r in d["reasons"])

    monkeypatch.setenv("J2GHA_ALLOW_INCOMPLETE_USAGE", "1")
    d = budget.guard(EST, yes=True)
    assert d["allowed"] and d["incomplete_usage_accepted"] and d["reasons"] == []


def test_runs_listing_error_is_recorded_not_counted_as_zero():
    def busy_runs(params):  # page 1: 100 runs of 10 min each; page 2 fails
        if params["page"] > 1:
            raise GitHubError(502, "Bad Gateway", "x")
        return {"workflow_runs": [{"id": i, "status": "completed"} for i in range(100)]}

    FakeGH.routes = {("GET", "/repos/me/busy/actions/runs"): busy_runs,
                     ("GET", r"/repos/me/busy/actions/runs/\d+/jobs"): {"jobs": [
                         {"started_at": "2026-10-01T00:00:00Z", "completed_at": "2026-10-01T00:10:00Z",
                          "labels": ["ubuntu-latest"]}]},
                     ("GET", "/repos/me/quiet/actions/runs"): {"workflow_runs": []}}
    t = budget.tally_month(FakeGH(), ["me/busy", "me/quiet"], refresh=True)
    assert t["per_repo"] == {"me/busy": 1000} and len(t["errors"]) == 1 and "me/busy" in t["errors"][0]

    route({("GET", "/users/me/settings/billing/usage/summary"): denied(404),
           ("GET", "/user/repos"): [{"full_name": "me/busy"}, {"full_name": "me/quiet"}],
           ("GET", "/repos/me/busy/actions/runs"): denied(502),
           ("GET", "/repos/me/quiet/actions/runs"): {"workflow_runs": []}})
    gh = FakeGH()
    u = budget.account_usage(gh, budget.target_account(gh, "me/harness"), budget.whoami(gh))
    assert u["complete"] is False and u["used"] == 0 and any("me/busy" in e for e in u["tally_errors"])


def test_fine_grained_token_without_scopes_header_still_queries_billing():
    route({("GET", "/user"): user(scopes=None),
           ("GET", "/users/me/settings/billing/usage/summary"): summary(1990)})
    d = budget.guard(EST, yes=True)
    assert called(r"/users/me/settings/billing/usage/summary")
    assert not called(r"/user/repos")  # no fallback tally
    assert d["usage"]["complete"] and d["usage"]["used"] == 1990 and d["usage"]["scopes"] == []
    assert not d["allowed"] and any("exceeds available" in r for r in d["reasons"])


def test_org_owned_repository_uses_the_organization_billing_endpoint(monkeypatch):
    monkeypatch.setenv("J2GHA_REPO", "acme/harness")
    FakeGH.routes = {("GET", "/user"): user(), ("GET", "/repos/acme/harness"): repo("acme", "Organization"),
                     ("GET", "/orgs/acme"): {"login": "acme", "plan": {"name": "team"}},
                     ("GET", "/organizations/acme/settings/billing/usage/summary"): summary(100)}
    d = budget.guard(EST, yes=True)
    assert d["allowed"] and d["account"]["owner"] == "acme" and d["usage"]["owner_type"] == "Organization"
    assert d["usage"]["included"] == 3000 and d["available_after_reserve"] == 3000 - 100 - 600
    assert not called(r"^/users/")

    # org billing not readable -> tally of the org's private repositories, marked incomplete
    FakeGH.routes.update({("GET", "/organizations/acme/settings/billing/usage/summary"): denied(),
                          ("GET", "/orgs/acme/repos"): [{"full_name": "acme/harness"}],
                          ("GET", "/repos/acme/harness/actions/runs"): {"workflow_runs": []}})
    d = budget.guard(EST, yes=True)
    assert not d["allowed"] and d["usage"]["complete"] is False
    assert called(r"^/orgs/acme/repos$")[-1][2]["type"] == "private"


def test_public_repository_skips_the_allowance_but_enforces_the_cap():
    FakeGH.routes = {("GET", "/repos/me/harness"): repo(private=False)}  # any billing/usage call would fail
    d = budget.guard(EST, yes=True, max_minutes=30)
    assert d["allowed"] and d["free_minutes"] and d["available_after_reserve"] is None
    d = budget.guard({"typical": 6, "worst_case": 45}, yes=True, max_minutes=30)
    assert not d["allowed"] and any("per-run cap of 30" in r for r in d["reasons"])
    assert [c[1] for c in FakeGH.calls] == ["/repos/me/harness", "/repos/me/harness"]


def test_unbounded_estimate_is_refused():
    FakeGH.routes = {("GET", "/repos/me/harness"): repo(private=False)}
    d = budget.guard({"typical": 1, "worst_case": 5, "unbounded": True}, yes=True)
    assert not d["allowed"] and any("cannot be bounded" in r for r in d["reasons"])


def test_unknown_billing_owner_fails_closed():
    FakeGH.routes = {("GET", "/repos/me/harness"): denied(404)}
    d = budget.guard(EST, yes=True)
    assert not d["allowed"] and any("billing owner" in r for r in d["reasons"])


def test_pending_reservations_reduce_available():
    route({("GET", "/users/me/settings/billing/usage/summary"): summary(1000)})
    write_ledger({"id": "p1", "status": "pending", "at": "2026-10-15T10:00:00+00:00", "owner": "me",
                  "reserved_minutes": 590},
                 {"id": "p2", "status": "pending", "at": "2026-10-15T10:00:00+00:00", "owner": "acme",
                  "reserved_minutes": 1000},  # another billing owner
                 {"id": "p3", "status": "pending", "at": "2026-09-30T10:00:00+00:00", "owner": "me",
                  "reserved_minutes": 1000},  # last month
                 {"id": "r1", "status": "reconciled", "at": "2026-10-15T10:00:00+00:00", "owner": "me",
                  "reserved_minutes": 1000, "billable_minutes": 3})
    d = budget.guard(EST, yes=True)
    # 2000 included - 1000 used - 590 reserved - 400 (20% reserve) = 10
    assert d["pending_minutes"] == 590 and d["available_after_reserve"] == 10
    assert not d["allowed"] and any("590 min of pending reservations" in r for r in d["reasons"])


def test_reserve_rechecks_allowance_under_the_lock():
    route()
    d = budget.guard(EST, yes=True)
    assert d["allowed"] and d["available_after_reserve"] == 2000 - 100 - 400
    first = budget.reserve(d, example="001", mode="trace", tier="hosted", repo="me/harness", branch="b1", sha="s1")
    assert first["status"] == "pending" and first["reserved_minutes"] == 30 and first["owner"] == "me"
    # a concurrent run reserved most of what was left after this decision was taken
    write_ledger(*budget.read_ledger(), {"id": "other", "status": "pending", "at": NOW.isoformat(), "owner": "me",
                                         "reserved_minutes": 1450})
    assert budget.reserve(d, example="001", mode="trace", tier="hosted", repo="me/harness", branch="b2",
                          sha="s2") is None
    assert [e["id"] for e in budget.read_ledger()] == [first["id"], "other"]


def test_ledger_writers_are_serialised(monkeypatch):
    decision = {"account": {"owner": "me"}, "free_minutes": True, "estimate": {"worst_case": 0},
                "available_after_reserve": None}
    real_read = budget.read_ledger

    def slow_read():  # widen the read-modify-write window so an unlocked writer would lose entries
        entries = real_read()
        time.sleep(0.002)
        return entries

    monkeypatch.setattr(budget, "read_ledger", slow_read)

    def writer(name):
        for i in range(20):
            budget.reserve(decision, example=f"{name}{i}")

    threads = [threading.Thread(target=writer, args=(n,)) for n in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    entries = real_read()
    assert len(entries) == 40 and len({e["id"] for e in entries}) == 40

    # a writer blocks while another process holds the lock
    done = threading.Event()
    with budget._ledger_lock():
        t = threading.Thread(target=lambda: (budget.update_reservation(entries[0]["id"], note="x"), done.set()))
        t.start()
        assert not done.wait(0.2)
    t.join(5)
    assert done.is_set() and real_read()[0]["note"] == "x"


def test_reconcile_and_report():
    route({("GET", "/repos/me/harness/actions/runs/7"): {"id": 7, "status": "completed", "conclusion": "success"},
           ("GET", "/repos/me/harness/actions/runs/8"): {"id": 8, "status": "completed", "conclusion": "failure"},
           ("GET", r"/repos/me/harness/actions/runs/[78]/jobs"): {"jobs": [
               {"started_at": "2026-10-15T10:00:00Z", "completed_at": "2026-10-15T10:02:30Z",
                "labels": ["ubuntu-latest"]}]},
           ("GET", "/repos/me/harness/actions/runs"): lambda p: {"workflow_runs": [
               {"id": 8, "head_sha": "abc"}] if p.get("head_sha") == "abc" else []}})
    base = {"status": "pending", "owner": "me", "repo": "me/harness", "reserved_minutes": 30, "example": "001",
            "mode": "full"}
    write_ledger({**base, "id": "a", "at": "2026-10-15T11:00:00+00:00", "run_id": 7},
                 {**base, "id": "b", "at": "2026-10-15T11:00:00+00:00", "sha": "abc"},
                 {**base, "id": "c", "at": "2026-10-14T08:00:00+00:00", "sha": "def"},  # > 24h, run never found
                 {"at": "2026-10-03T08:00:00+00:00", "example": "002", "mode": "trace", "run_id": 3,
                  "billable_minutes": 4})  # legacy line (no status)
    r = budget.report()
    by_id = {e.get("id"): e for e in budget.read_ledger()}
    assert by_id["a"]["status"] == "reconciled" and by_id["a"]["billable_minutes"] == 3
    assert by_id["b"]["status"] == "reconciled" and by_id["b"]["run_id"] == 8 and by_id["b"]["result"] == "failure"
    assert by_id["c"]["status"] == "pending"
    assert r["pending_minutes"] == 30 and r["stale"] == ["c"] and r["harness_runs"] == 3 and r["harness_minutes"] == 10
    assert r["remaining"] == 2000 - 100 - 30
    text = r["text"]
    assert "for me (user)" in text and "me/harness (private)" in text and "usage data: complete" in text
    assert "pending reservations: 1, 30 min" in text and "WARNING: 1 reservation(s) older than 24h" in text
    assert "c (no run id, sha def)" in text
    json.dumps(r)  # `j2gha budget --json`

    assert budget.clear_reservations(["c"]) == 1
    assert budget.report()["pending_minutes"] == 0
