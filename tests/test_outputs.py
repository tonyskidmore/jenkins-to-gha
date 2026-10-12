"""Full-mode output contracts (Phase 4, P4.1): archived files and test results, Jenkins vs the converted run."""

import io
import zipfile

import pytest

from j2gha import outputs
from j2gha.gha import remote
from j2gha.runners import execute

JUNIT = b"""<?xml version="1.0" encoding="utf-8"?>
<testsuite name="tests.unit" tests="4">
  <testcase classname="tests.unit.CoreTest" name="test_add"/>
  <testcase classname="tests.unit.CoreTest" name="test_remove"><failure message="boom">trace</failure></testcase>
  <testcase name="test_no_class"><error message="x"/></testcase>
  <testcase classname="tests.unit.CoreTest" name="test_later"><skipped/></testcase>
</testsuite>"""

MODEL = {"jobs": {
    "build": {"steps": [
        {"uses": "actions/upload-artifact@sha", "with": {"name": "stash-dist", "path": "dist/**"},
         "_j2gha": {"kind": "stash"}},
        {"uses": "actions/upload-artifact@sha", "with": {"name": "test-reports-17", "path": "r/junit.xml"},
         "_j2gha": {"kind": "junit-upload"}},
        {"uses": "actions/upload-artifact@sha", "with": {"name": "artifacts-4", "path": "dist/*.tgz"},
         "_j2gha": {"kind": "archiveArtifacts", "root": ""}},
    ]},
    "compat": {"strategy": {"matrix": {"OS": ["a", "b"]}}, "steps": [
        {"uses": "actions/upload-artifact@sha", "with": {"name": "artifacts-9-${{ matrix.OS }}",
                                                          "path": "${{ matrix.OS }}/x.txt"},
         "_j2gha": {"kind": "archiveArtifacts", "root": ""}},
    ]},
}}


def zipped(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_junit_cases_follow_the_jenkins_junit_plugin():
    cases = outputs.parse_junit(JUNIT)
    assert cases == [
        {"class": "tests.unit.CoreTest", "name": "test_add", "status": "passed"},
        {"class": "tests.unit.CoreTest", "name": "test_remove", "status": "failed"},
        {"class": "tests.unit", "name": "test_no_class", "status": "failed"},  # no classname: the suite's name
        {"class": "tests.unit.CoreTest", "name": "test_later", "status": "skipped"},
    ]
    wrapped = b"<testsuites>" + JUNIT.split(b"?>", 1)[1] + b"</testsuites>"
    assert outputs.parse_junit(wrapped) == cases


def test_jenkins_statuses_are_normalised():
    report = {"suites": [{"cases": [{"className": "C", "name": n, "status": s} for n, s in
                                    [("a", "PASSED"), ("b", "FIXED"), ("c", "FAILED"), ("d", "REGRESSION"),
                                     ("e", "SKIPPED")]]}]}
    assert [c["status"] for c in outputs.jenkins_cases(report)] == ["passed", "passed", "failed", "failed", "skipped"]


def test_artifacts_are_classified_by_the_upload_step_that_made_them():
    kinds = outputs.upload_kinds(MODEL)
    assert outputs.artifact_kind("artifacts-4", kinds) == "archiveArtifacts"
    assert outputs.artifact_kind("artifacts-41", kinds) is None  # another step's name, not a prefix match
    assert outputs.artifact_kind("artifacts-9-b", kinds) == "archiveArtifacts"  # matrix cell suffix
    assert outputs.artifact_kind("test-reports-17", kinds) == "junit-upload"
    assert not outputs.wanted(outputs.artifact_kind("stash-dist", kinds))  # Jenkins does not archive stashes


def gha(**artifacts):
    return outputs.gha_outputs({k.replace("_", "-"): zipped(v) for k, v in artifacts.items()}, MODEL)


def jenkins(archived, tests):
    return {"archived": [outputs.file_entry(p, d) for p, d in archived.items()], "tests": tests}


def test_gha_outputs_read_archives_and_junit_and_ignore_stashes():
    out = gha(stash_dist={"a.tgz": b"x"}, test_reports_17={"junit.xml": JUNIT}, artifacts_4={"dist/app.tgz": b"bin"})
    assert [f["path"] for f in out["archived"]] == ["dist/app.tgz"]
    assert len(out["tests"]) == 4 and "problems" not in out
    broken = outputs.gha_outputs({"test-reports-17": zipped({"junit.xml": b"<oops"})}, MODEL)
    assert broken["problems"] and broken["tests"] is None


CASES = outputs.parse_junit(JUNIT)


def test_same_outputs_compare_same_even_when_content_differs():
    # builds are not reproducible: content hashes are shown, not counted (decision D1)
    j = jenkins({"dist/app.tgz": b"jenkins build"}, CASES)
    c = outputs.compare_outputs(j, gha(test_reports_17={"junit.xml": JUNIT},
                                       artifacts_4={"dist/app.tgz": b"gha build"}))
    assert c["verdict"] == "same"
    assert c["archived"]["content_differs"] == ["dist/app.tgz"] and c["archived"]["content_same"] == 0


def test_the_harness_own_workflow_file_is_never_an_extra_archived_file():
    # an archive of '**' on the run branch picks up the workflow the harness pushed there (013); Jenkins has no such file
    j = jenkins({"dist/app.tgz": b"x"}, CASES)
    c = outputs.compare_outputs(j, gha(test_reports_17={"junit.xml": JUNIT},
                                       artifacts_4={"dist/app.tgz": b"x", ".github/workflows/j2gha-run.yml": b"on: push"}))
    assert c["verdict"] == "same" and c["archived"]["extra"] == [] and c["archived"]["gha"] == 1


@pytest.mark.parametrize("archived, tests, what", [
    ({"dist/app.tgz": b"x", "dist/app.tgz.sha256": b"y"}, CASES, "archived"),  # a file Jenkins archived is missing
    ({}, CASES, "archived"),  # the converted run archived a file Jenkins did not
    ({"dist/app.tgz": b"x"}, [{**c, "status": "passed"} for c in CASES], "tests"),  # same cases, other status
    ({"dist/app.tgz": b"x"}, CASES[:2], "tests"),  # fewer cases
    ({"dist/app.tgz": b"x"}, None, "tests"),  # Jenkins recorded no test report at all
])
def test_differences_in_tests_or_the_archived_set_differ(archived, tests, what):
    c = outputs.compare_outputs(jenkins(archived, tests),
                                gha(test_reports_17={"junit.xml": JUNIT}, artifacts_4={"dist/app.tgz": b"x"}))
    assert c["verdict"] == "differs" and c[what]["status"] == "differs"
    assert c["archived" if what == "tests" else "tests"]["status"] in ("same", "none")


def test_matrix_copies_of_one_archived_file_match_once():
    j = jenkins({"out/x.txt": b"b"}, None)
    g = outputs.gha_outputs({"artifacts-9-a": zipped({"out/x.txt": b"a"}), "artifacts-9-b": zipped({"out/x.txt": b"b"})},
                            MODEL)
    c = outputs.compare_outputs(j, g)
    assert c["verdict"] == "same" and c["archived"]["content_same"] == 1 and c["archived"]["copies"] == 1
    assert c["tests"]["status"] == "none"


def test_unreadable_outputs_are_inconclusive_never_same():
    j = jenkins({"dist/app.tgz": b"x"}, None)
    g = outputs.gha_outputs({"artifacts-4": zipped({"dist/app.tgz": b"x"})}, MODEL, ["test-reports-17: over the cap"])
    assert outputs.compare_outputs(j, g)["verdict"] == "inconclusive"
    assert outputs.compare_outputs(None, g)["verdict"] == "inconclusive"


def _ref(outs):
    return {"result": "SUCCESS", "stages": [{"name": "Build", "status": "SUCCESS"}], "outputs": outs}


def _rec(outs):
    return {"result": "success", "jobs": [{"name": "build"}], "outputs": outs}


def test_full_mode_verdict_counts_the_outputs():
    j = jenkins({"dist/app.tgz": b"x"}, CASES)
    same = gha(test_reports_17={"junit.xml": JUNIT}, artifacts_4={"dist/app.tgz": b"y"})
    assert execute.compare_outcome(_ref(j), _rec(same), MODEL)["verdict"] == "equivalent"
    no_tests = gha(artifacts_4={"dist/app.tgz": b"y"})
    c = execute.compare_outcome(_ref(j), _rec(no_tests), MODEL)
    assert c["verdict"] == "differs" and c["outputs"]["tests"]["status"] == "differs"
    broken = {**same, "problems": ["artifacts-4: not downloaded"]}
    c = execute.compare_outcome(_ref(j), _rec(broken), MODEL)
    assert c["verdict"] == "inconclusive" and "outputs" in c["inconclusive"]["reason"]
    assert "tests same" in outputs.summary(execute.compare_outcome(_ref(j), _rec(same), MODEL)["outputs"])


def test_a_full_mode_reference_without_outputs_is_not_usable():
    base = {"jenkinsfile_sha256": "h", "scenario": {"branch": "main"}, "mode": "full"}
    ref = {"result": "SUCCESS", "provenance": {"jenkinsfile_sha256": "h", "scenario": {"branch": "main"},
                                               "localizer_version": execute.LOCALIZER_VERSION}}
    assert "no archived files" in (execute.reference_problem(ref, base) or "")
    assert execute.reference_problem({**ref, "outputs": {"archived": [], "tests": None}}, base) is None
    assert execute.reference_problem(ref, {**base, "mode": "trace"}) is None


class FakeGH:
    def __init__(self, listing):
        self.listing, self.downloads = listing, []

    def get(self, path, **k):
        return self.listing

    def request(self, method, url, **k):
        self.downloads.append(url)
        return type("R", (), {"content": zipped({"junit.xml": JUNIT})})()


def test_remote_runs_download_only_the_artifacts_that_are_compared():
    gh = FakeGH({"artifacts": [
        {"name": "stash-dist", "size_in_bytes": 10, "archive_download_url": "u/stash"},
        {"name": "test-reports-17", "size_in_bytes": 10, "archive_download_url": "u/junit"},
        {"name": "artifacts-4", "size_in_bytes": 10 ** 12, "archive_download_url": "u/huge"},
    ]})
    out = remote.run_outputs(gh, "me/harness", 1, MODEL)
    assert gh.downloads == ["u/junit"]
    assert len(out["tests"]) == 4 and out["problems"] == ["artifacts-4: over the download cap"]


def test_act_outputs_read_the_artifact_server_directory(tmp_path):
    for name, files in {"artifacts-4": {"dist/app.tgz": b"x"}, "stash-dist": {"a": b"y"},
                        "test-reports-17": {"junit.xml": JUNIT}}.items():
        (tmp_path / "1" / name).mkdir(parents=True)
        (tmp_path / "1" / name / f"{name}.zip").write_bytes(zipped(files))
    out = outputs.act_outputs(tmp_path, MODEL)
    assert [(f["path"], f["artifact"]) for f in out["archived"]] == [("dist/app.tgz", "artifacts-4")]
    assert len(out["tests"]) == 4


# ------------------------------------------------------------------------------- review of Phase 4 (findings 1, 4-6)
def test_one_converted_file_cannot_stand_for_two_jenkins_files():
    """Paths are compared as Jenkins archives them: a stripped `app.tgz` is neither `linux/app.tgz` nor
    `windows/app.tgz`."""
    j = jenkins({"linux/app.tgz": b"linux", "windows/app.tgz": b"windows"}, None)
    c = outputs.compare_outputs(j, {"archived": [outputs.file_entry("app.tgz", b"linux")], "tests": None})
    assert c["verdict"] == "differs" and c["archived"]["missing"] == ["linux/app.tgz", "windows/app.tgz"]
    both = {"archived": [outputs.file_entry("linux/app.tgz", b"l"), outputs.file_entry("windows/app.tgz", b"w")],
            "tests": None}
    assert outputs.compare_outputs(j, both)["verdict"] == "same"


# ------------------------------------------------------------- follow-up review of Phase 4 (finding 1: identity)
def test_matrix_copies_cannot_conceal_a_missing_file():
    """Follow-up finding 1: both cells archive linux/app.tgz (a conversion bug), Jenkins archived one per platform.
    The two copies are one logical file: windows/app.tgz is missing."""
    j = jenkins({"linux/app.tgz": b"linux", "windows/app.tgz": b"windows"}, None)
    g = outputs.gha_outputs({"artifacts-9-linux": zipped({"linux/app.tgz": b"linux"}),
                             "artifacts-9-windows": zipped({"linux/app.tgz": b"linux"})}, MODEL)
    c = outputs.compare_outputs(j, g)
    assert c["verdict"] == "differs" and c["archived"]["missing"] == ["windows/app.tgz"]
    assert c["archived"]["copies"] == 1 and c["archived"]["extra"] == []
    # the correct conversion: one platform per cell, the same file name in both artifacts
    ok = outputs.gha_outputs({"artifacts-9-linux": zipped({"linux/app.tgz": b"linux"}),
                              "artifacts-9-windows": zipped({"windows/app.tgz": b"windows"})}, MODEL)
    c = outputs.compare_outputs(j, ok)
    assert c["verdict"] == "same" and c["archived"]["copies"] == 0 and c["archived"]["content_same"] == 2


def test_an_archive_uploaded_without_the_jenkins_paths_is_not_compared():
    """A model converted before archive steps recorded their Jenkins directory uploads stripped paths: they can
    neither match nor miss a Jenkins file, so the comparison is inconclusive, never same or differs."""
    legacy = {"jobs": {"build": {"steps": [{"uses": "actions/upload-artifact@sha",
                                            "with": {"name": "artifacts-4", "path": "dist/*.tgz"},
                                            "_j2gha": {"kind": "archiveArtifacts"}}]}}}
    g = outputs.gha_outputs({"artifacts-4": zipped({"app.tgz": b"x"})}, legacy)
    assert g["archived"] == [] and "re-run `j2gha convert`" in g["problems"][0]
    c = outputs.compare_outputs(jenkins({"dist/app.tgz": b"x"}, None), g)
    assert c["verdict"] == "inconclusive"


def test_full_mode_variants_upload_archives_under_their_jenkins_paths():
    """The converted archive step records the dir() it ran in; the full-mode variant adds a pattern there that
    matches nothing, so upload-artifact's common directory - the artifact root - is the Jenkins archive directory."""
    from j2gha.convert.generator import convert
    from j2gha.ir import Agent, Pipeline, Stage, Step
    from j2gha.runners.variants import make_variant
    ir = Pipeline(dialect="declarative", agent=Agent("any"), options={"skipDefaultCheckout": True}, stages=[
        Stage("Build", steps=[Step("archiveArtifacts", named={"artifacts": "top.txt"}),
                              Step("dir", args=["sub"], body=[Step("archiveArtifacts", named={"artifacts": "out/*.tgz"})])])])
    model = convert(ir, "")["workflow"]
    full, _ = make_variant(model, "full", "act", {"branch": "main"})
    def own(path):  # without Ant's default excludes (negated patterns do not move upload-artifact's root)
        return [line for line in path.splitlines() if not line.startswith("!")]
    paths = [own(s["with"]["path"]) for s in full["jobs"]["build"]["steps"]
             if s.get("uses", "").startswith("actions/upload-artifact")]
    assert paths == [["top.txt", ".j2gha-artifact-root"], ["sub/out/*.tgz", "sub/.j2gha-artifact-root"]]
    # the conversion itself is unchanged
    assert [own(s["with"]["path"]) for s in model["jobs"]["build"]["steps"] if "with" in s] == [["top.txt"], ["sub/out/*.tgz"]]


def test_failed_collection_is_inconclusive_not_a_difference():
    j = jenkins({"linux/app.tgz": b"x"}, CASES)
    failed = {"archived": [], "tests": None, "problems": ["artifacts-4: not downloaded"]}
    c = outputs.compare_outputs(j, failed)
    assert c["verdict"] == "inconclusive" and "not downloaded" in c["reason"]
    assert c["problems"]["gha"] == ["artifacts-4: not downloaded"]
    # an incomplete Jenkins side cannot show that the converted run has too much
    c = outputs.compare_outputs({**j, "problems": ["over the cap"]},
                                {"archived": [outputs.file_entry("linux/app.tgz", b"x"), outputs.file_entry("extra", b"")],
                                 "tests": CASES})
    assert c["verdict"] == "inconclusive"


def test_differences_the_evidence_proves_still_count_when_collection_was_incomplete():
    j = jenkins({"dist/app.tgz": b"x"}, CASES)
    flipped = [{**c, "status": "passed"} if c["name"] == "test_remove" else c for c in CASES]
    partial = {"archived": [], "tests": flipped, "problems": ["artifacts-4: not downloaded"]}
    assert outputs.compare_outputs(j, partial)["verdict"] == "differs"  # same case, another status
    surplus = {"archived": [outputs.file_entry("dist/app.tgz", b"x"), outputs.file_entry("surprise.bin", b"")],
               "tests": None, "problems": ["test-reports-17: not downloaded"]}
    assert outputs.compare_outputs(j, surplus)["verdict"] == "differs"  # Jenkins complete: the extra file is real


class Body:
    def __init__(self, data, length=True, status=200):
        self.data, self.status_code, self.closed = data, status, False
        self.headers = {"Content-Length": str(len(data))} if length else {}

    def iter_content(self, chunk_size):
        for i in range(0, len(self.data), 3):
            yield self.data[i:i + 3]

    def close(self):
        self.closed = True

    def json(self):
        return self.data


@pytest.mark.parametrize("length", [True, False], ids=["content-length", "no-content-length"])
def test_jenkins_files_over_the_cap_make_the_comparison_inconclusive(length):
    from j2gha.jenkins.controller import Jenkins

    class Session:
        def get(self, url, **k):
            if "/artifact/" in url:
                return Body(b"0123456789", length=length)
            if "/testReport/" in url:
                return Body({}, status=404)
            return Body({"artifacts": [{"relativePath": "app.tgz"}]})

    j = object.__new__(Jenkins)
    j.s, j.base = Session(), "http://unused"
    out = j.build_outputs("job", 1, cap=4)
    assert out["archived"] == [{"path": "app.tgz", "size": None, "sha256": None}]
    assert out["problems"] and "download cap" in out["problems"][0] and out["tests"] is None
    g = {"archived": [outputs.file_entry("app.tgz", b"0123456789")], "tests": None}
    assert outputs.compare_outputs(out, g)["verdict"] == "inconclusive"
    assert j.build_outputs("job", 1, cap=100)["archived"][0]["sha256"] is not None


def test_remote_artifact_listing_reads_every_page():
    pages = []

    class Paged(FakeGH):
        def get(self, path, **k):
            page = k["params"]["page"]
            pages.append(page)
            if page == 1:
                return {"total_count": 101, "artifacts": [{"name": f"j2gha-ws-{i}"} for i in range(100)]}
            return {"total_count": 101, "artifacts": [{"name": "test-reports-17", "size_in_bytes": 10,
                                                        "archive_download_url": "u/junit"}]}

    gh = Paged({})
    out = remote.run_outputs(gh, "me/harness", 1, MODEL)
    assert pages == [1, 2] and gh.downloads == ["u/junit"] and len(out["tests"]) == 4


def test_build_tag_in_an_archive_path_is_each_runs_own_identity():
    # `logdir/${BUILD_TAG}/...` (example 107): each side's tag is unique to its run, so it is compared as a placeholder
    j = jenkins({"logdir/jenkins-ex-107-full-6/op.log": b"x"}, CASES)
    for tag in ("gha-tonyskidmore-jenkins-to-gha-67", "gha-nektos--1"):  # remote run, act
        c = outputs.compare_outputs(j, gha(test_reports_17={"junit.xml": JUNIT},
                                           artifacts_4={f"logdir/{tag}/op.log": b"x"}))
        assert c["verdict"] == "same", c["archived"]
    # an ordinary directory, or a bare number, is not a run tag
    j = jenkins({"logdir/6/op.log": b"x", "gha-docs/a.txt": b"y"}, CASES)
    c = outputs.compare_outputs(j, gha(test_reports_17={"junit.xml": JUNIT},
                                       artifacts_4={"logdir/67/op.log": b"x", "gha-docs/a.txt": b"y"}))
    assert c["verdict"] == "differs" and c["archived"]["missing"] == ["logdir/6/op.log"]
