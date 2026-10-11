"""Full-mode output contracts: the archived files and test results of a run, compared across Jenkins and GHA.

Jenkins side: the build's archived artifacts (`archiveArtifacts`) and its test report (`junit`), read from the REST API.
GHA side: the run's artifacts, classified through the workflow model by the upload step that made them
(`archiveArtifacts`/`archive` -> archived files, `junit-upload` -> JUnit XML). Stashes, HTML reports and workspace
hand-offs are not archived by Jenkins and are not compared.

What counts toward the verdict (Phase 4, decision D1): the test cases (same cases, same status) and the *set* of archived
files. Content hashes are recorded and shown but do not change the verdict: builds are not reproducible (archive
timestamps, BUILD_NUMBER vs github.run_number).

File identity is the path Jenkins archives under: relative to the directory `archiveArtifacts` ran in (`dir()`).
upload-artifact stores files relative to its patterns' common directory instead, which would drop the path that tells
`linux/app.tgz` from `windows/app.tgz`. The converter records that directory on the upload step (`_j2gha.root`) and
full-mode execution variants add a pattern for ROOT_MARKER in it (it matches nothing): the common directory becomes the
Jenkins one, and the uploaded paths are Jenkins' paths. An archive made without it (a model converted before) is not
compared: its paths prove nothing.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

# total bytes downloaded per side; larger files keep their path and size but get no hash
DOWNLOAD_CAP = 200 * 1024 * 1024
ARCHIVE_KINDS = {"archiveArtifacts", "archive"}
TEST_KINDS = {"junit-upload"}
# Jenkins CaseResult.Status -> passed | failed | skipped
JENKINS_STATUS = {"PASSED": "passed", "FIXED": "passed", "FAILED": "failed", "REGRESSION": "failed",
                  "SKIPPED": "skipped"}
MAX_LISTED = 20
# a path in the Jenkins archive directory that no upload matches: it only moves upload-artifact's root there
ROOT_MARKER = ".j2gha-artifact-root"


def file_entry(path: str, data: bytes | None, size: int | None = None) -> dict[str, Any]:
    return {"path": path, "size": len(data) if data is not None else size,
            "sha256": hashlib.sha256(data).hexdigest() if data is not None else None}


def case(class_name: str, name: str, status: str) -> dict[str, str]:
    return {"class": class_name, "name": name, "status": status}


def parse_junit(data: bytes) -> list[dict[str, str]]:
    """Test cases of a JUnit XML report, as Jenkins' junit plugin reads them: a case without `classname` takes its
    suite's name; a `failure` or `error` child fails it, a `skipped` child skips it."""
    root = ET.fromstring(data)
    out = []

    def walk(el: ET.Element, suite: str) -> None:
        for child in el:
            if child.tag == "testsuite":
                walk(child, child.get("name", ""))
            elif child.tag == "testcase":
                tags = {c.tag for c in child}
                status = "failed" if tags & {"failure", "error"} else "skipped" if "skipped" in tags else "passed"
                out.append(case(child.get("classname") or suite, child.get("name", ""), status))
    if root.tag == "testsuite":
        walk(root, root.get("name", ""))
    else:
        walk(root, "")
    return out


def jenkins_cases(report: dict[str, Any]) -> list[dict[str, str]]:
    """Cases of Jenkins' `testReport/api/json`."""
    return [case(c.get("className", ""), c.get("name", ""), JENKINS_STATUS.get(str(c.get("status")), "failed"))
            for s in report.get("suites") or [] for c in s.get("cases") or []]


def upload_kinds(model: dict[str, Any] | None) -> list[tuple[re.Pattern[str], str, bool]]:
    """(artifact-name pattern, step kind, rooted) for every upload step of the workflow model. Names built from
    expressions (`test-reports-37-${{ matrix.OS }}`) match any value in place of the expression. *rooted*: the step
    records the Jenkins archive directory, so execution variants upload Jenkins' paths (`root_marker`)."""
    out = []
    for job in ((model or {}).get("jobs") or {}).values():
        for st in job.get("steps", []):
            if not str(st.get("uses", "")).startswith("actions/upload-artifact@"):
                continue
            name = str((st.get("with") or {}).get("name", "artifact"))
            parts = re.split(r"\$\{\{.*?\}\}", name)
            meta = st.get("_j2gha") or {}
            out.append((re.compile("^" + ".+".join(re.escape(p) for p in parts) + "$"), str(meta.get("kind", "")),
                        "root" in meta))
    return out


def artifact_kind(name: str, kinds: list[tuple[re.Pattern[str], str, bool]]) -> str | None:
    return next((k for pattern, k, _ in kinds if pattern.match(name)), None)


def _rooted(name: str, kinds: list[tuple[re.Pattern[str], str, bool]]) -> bool:
    return next((r for pattern, _, r in kinds if pattern.match(name)), False)


def root_marker(meta: dict[str, Any]) -> str | None:
    """The `path` line an execution variant adds to an archive upload so that upload-artifact stores files relative to
    the Jenkins archive directory (None: the step does not record it)."""
    if "root" not in meta:
        return None
    root = str(meta["root"]).strip("/")
    return f"{root}/{ROOT_MARKER}" if root not in ("", ".") else ROOT_MARKER


def wanted(kind: str | None) -> bool:
    return kind in ARCHIVE_KINDS or kind in TEST_KINDS


def gha_outputs(artifacts: dict[str, bytes | None], model: dict[str, Any] | None,
                skipped: list[str] | None = None, injected: dict[str, str] | None = None) -> dict[str, Any]:
    """Outputs of a GHA run from its artifacts ({artifact name: zip bytes, or None when not downloaded}).
    ``injected``: the files the harness itself put in the run's workspace ({path: workflow text}), recorded with
    their hashes so the comparison can tell them from the project's own files."""
    kinds = upload_kinds(model)
    archived: list[dict[str, Any]] = []
    tests: list[dict[str, str]] | None = None
    problems = list(skipped or [])
    for name in sorted(artifacts):
        kind = artifact_kind(name, kinds)
        if not wanted(kind):
            continue
        blob = artifacts[name]
        if blob is None:
            problems.append(f"{name}: not downloaded")
            continue
        if kind in ARCHIVE_KINDS and not _rooted(name, kinds):
            problems.append(f"{name}: uploaded without the Jenkins archive paths (converted before they were kept: "
                            "re-run `j2gha convert`)")
            continue
        try:
            z = zipfile.ZipFile(io.BytesIO(blob))
        except zipfile.BadZipFile:
            problems.append(f"{name}: not a zip archive")
            continue
        for info in z.infolist():
            if info.is_dir():
                continue
            data = z.read(info)
            if kind in ARCHIVE_KINDS:
                archived.append({**file_entry(info.filename, data), "artifact": name})
            else:
                try:
                    tests = (tests or []) + parse_junit(data)
                except ET.ParseError as e:
                    problems.append(f"{name}/{info.filename}: unreadable JUnit XML ({e})")
    out: dict[str, Any] = {"archived": archived, "tests": tests}
    if injected:
        out["injected"] = [file_entry(path, text.encode()) for path, text in sorted(injected.items())]
    if problems:
        out["problems"] = problems
    return out


def act_outputs(root: Path, model: dict[str, Any] | None, injected: dict[str, str] | None = None) -> dict[str, Any]:
    """Outputs of an act run from its artifact server directory (`<root>/<run>/<name>/<name>.zip`)."""
    kinds = upload_kinds(model)
    blobs: dict[str, bytes | None] = {z.parent.name: z.read_bytes() for z in sorted(root.glob("*/*/*.zip"))
                                      if wanted(artifact_kind(z.parent.name, kinds))}
    return gha_outputs(blobs, model, injected=injected)


def compare_outputs(jenkins: dict[str, Any] | None, gha: dict[str, Any] | None) -> dict[str, Any]:
    """{"verdict": same | differs | inconclusive, "reason", "tests": {...}, "archived": {...}}.

    A side whose collection had problems (a download failed, a file was over the cap) is incomplete: what it lacks
    may be lost evidence rather than a missing output. A difference only counts when the evidence for it is complete -
    a file or case the converted run lacks needs a complete converted collection, one only the converted run has needs
    a complete Jenkins collection, a status change needs the case on both sides. Otherwise it is inconclusive."""
    if not jenkins or not gha:
        return {"verdict": "inconclusive", "reason": "outputs not recorded on " +
                ("either side" if not jenkins and not gha else "the Jenkins side" if not jenkins else "the GHA side")}
    j_problems, g_problems = list(jenkins.get("problems") or []), list(gha.get("problems") or [])
    complete = {"jenkins": not j_problems, "gha": not g_problems}
    tests = _compare_tests(jenkins.get("tests"), gha.get("tests"), complete)
    archived = _compare_archived(jenkins.get("archived") or [], gha.get("archived") or [], complete,
                                 gha.get("injected"))
    out: dict[str, Any] = {"tests": tests, "archived": archived}
    if j_problems or g_problems:
        out["problems"] = {"jenkins": j_problems, "gha": g_problems}
    if tests.get("proven") or archived.get("proven"):
        out["verdict"] = "differs"
    elif j_problems or g_problems:
        out.update(verdict="inconclusive", reason="; ".join([*j_problems, *g_problems][:5]))
    else:
        out["verdict"] = "same"
    return out


def _compare_tests(j: list[dict[str, str]] | None, g: list[dict[str, str]] | None,
                   complete: dict[str, bool]) -> dict[str, Any]:
    if j is None and g is None:
        return {"status": "none"}
    if j is None or g is None:
        # one side has no report at all: proven only if the side without one collected everything
        return {"status": "differs", "jenkins": None if j is None else _totals(j),
                "gha": None if g is None else _totals(g), "proven": complete["jenkins" if j is None else "gha"],
                "reason": "only the " + ("converted run" if j is None else "Jenkins run") + " recorded test results"}
    cj, cg = Counter(_key(c) for c in j), Counter(_key(c) for c in g)
    out: dict[str, Any] = {"status": "same" if cj == cg else "differs", "jenkins": _totals(j), "gha": _totals(g)}
    if cj == cg:
        return out
    out["only_jenkins"] = [list(k) for k in sorted((cj - cg).elements())][:MAX_LISTED]
    out["only_gha"] = [list(k) for k in sorted((cg - cj).elements())][:MAX_LISTED]
    ids_j, ids_g = Counter(k[:2] for k in cj.elements()), Counter(k[:2] for k in cg.elements())
    # the same case, as often on both sides, with other statuses: a difference however incomplete the rest is
    changed = [i for i in ids_j if ids_j[i] == ids_g.get(i) and
               Counter(k[2] for k in cj.elements() if k[:2] == i) != Counter(k[2] for k in cg.elements() if k[:2] == i)]
    lacking, surplus = ids_j - ids_g, ids_g - ids_j
    out["proven"] = bool(changed or (lacking and complete["gha"]) or (surplus and complete["jenkins"]))
    return out


def _key(c: dict[str, str]) -> tuple[str, str, str]:
    return c["class"], c["name"], c["status"]


def _totals(cases: list[dict[str, str]]) -> dict[str, int]:
    t = Counter(c["status"] for c in cases)
    return {"cases": len(cases), **{s: t.get(s, 0) for s in ("passed", "failed", "skipped")}}


# The harness's own workflow files on the run branch (runners.act, gha.remote). Records made before the injected files
# were recorded (`injected`) are filtered by these paths, and only when Jenkins did not archive the path itself.
HARNESS_FILES = frozenset({".github/workflows/j2gha.yml", ".github/workflows/j2gha-run.yml"})


def _harness_file(f: dict[str, Any], injected: list[dict[str, Any]] | None, jenkins: dict[str, Any]) -> bool:
    """Is this converted-side file the harness's own workflow file? An archive of `**` picks that up on the converted
    side only. It is identified by path *and* content (what the harness wrote), and never when Jenkins archived the
    same path: a project's own file of that name is then compared like any other (review R8-7)."""
    if f["path"] in jenkins:
        return False
    if injected is None:
        return f["path"] in HARNESS_FILES
    return any(i["path"] == f["path"] and i.get("sha256") and i.get("sha256") == f.get("sha256") for i in injected)


def _compare_archived(j: list[dict[str, Any]], g: list[dict[str, Any]], complete: dict[str, bool],
                      injected: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Files are identified by their Jenkins archive path on both sides (see the module docstring). Converted files
    with the same path are copies of one logical file - matrix cells upload the same path, Jenkins keeps one - and are
    grouped before anything is compared, so a copy never stands in for another Jenkins file."""
    jenkins: dict[str, dict[str, Any]] = {f["path"]: f for f in j}  # Jenkins keeps one file per path
    converted: dict[str, list[dict[str, Any]]] = {}
    g = [f for f in g if not _harness_file(f, injected, jenkins)]
    for f in g:
        converted.setdefault(f["path"], []).append(f)
    missing = sorted(set(jenkins) - set(converted))
    extra = sorted(set(converted) - set(jenkins))
    copies = sum(len(fs) - 1 for fs in converted.values())
    content: dict[str, Any] = {"same": 0, "differs": [], "unknown": 0}
    for path in sorted(set(jenkins) & set(converted)):
        a, bs = jenkins[path].get("sha256"), {f.get("sha256") for f in converted[path]} - {None}
        if a is None or not bs:
            content["unknown"] += 1
        elif a in bs:  # Jenkins kept one of the copies
            content["same"] += 1
        else:
            content["differs"].append(path)
    status = "none" if not j and not g else "differs" if missing or extra else "same"
    return {"status": status, "jenkins": len(j), "gha": len(g), "missing": missing[:MAX_LISTED],
            "extra": extra[:MAX_LISTED], "copies": copies, "content_same": content["same"],
            "content_differs": content["differs"][:MAX_LISTED], "content_unknown": content["unknown"],
            "proven": bool((missing and complete["gha"]) or (extra and complete["jenkins"]))}


def summary(cmp: dict[str, Any]) -> str:
    """One line for the README: tests and archived files."""
    if cmp.get("verdict") == "inconclusive" and "tests" not in cmp:
        return f"outputs not compared ({cmp.get('reason')})"
    parts = []
    t = cmp["tests"]
    if t["status"] == "none":
        parts.append("no test results on either side")
    elif t.get("jenkins") and t.get("gha"):
        parts.append(f"tests {t['status']} (Jenkins {_fmt(t['jenkins'])}; converted {_fmt(t['gha'])})")
    else:
        parts.append(f"tests differ: {t.get('reason')}")
    a = cmp["archived"]
    if a["status"] == "none":
        parts.append("nothing archived on either side")
    else:
        parts.append(f"archived files {a['status']} ({a['jenkins']} Jenkins, {a['gha']} converted"
                     + (f"; missing {', '.join(a['missing'][:5])}" if a["missing"] else "")
                     + (f"; extra {', '.join(a['extra'][:5])}" if a["extra"] else "")
                     + f"; content: {a['content_same']} same, {len(a['content_differs'])} differ"
                     + (f", {a['content_unknown']} not hashed" if a["content_unknown"] else "") + ")")
    return "; ".join(parts)


def _fmt(t: dict[str, int]) -> str:
    return f"{t['cases']} cases, {t['failed']} failed, {t['skipped']} skipped"
