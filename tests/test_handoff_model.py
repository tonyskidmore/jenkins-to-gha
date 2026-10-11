"""The workspace hand-off against a reference model (follow-up review of Phase 4, findings 2-4).

Each test converts a pipeline, runs the generated hand-off and `sh` steps job by job (`handoff_sim`) and compares
the workspace a job starts from with Jenkins' one workspace at that point (every earlier stage's script run in
declaration order). Concurrent branches here never touch the same path, except in the conflict tests, so job order and
Jenkins' order agree; the seeded scenarios combine pipeline shapes with file, directory, mode, symlink and type
changes."""

import random
import shutil

import pytest

from handoff_sim import StepFailed, build, jenkins, simulate
from j2gha.convert import workspace
from j2gha.convert.generator import convert
from j2gha.ir import Agent, Condition, Pipeline, Stage, Step, When

pytestmark = pytest.mark.skipif(not (shutil.which("bash") and shutil.which("tar")), reason="needs bash and GNU tar")


def sh(cmd):
    return Step("sh", args=[cmd])


def jobs_of(stages, checkout=True):
    ir = Pipeline(dialect="declarative", agent=Agent("any"), options={} if checkout else {"skipDefaultCheckout": True},
                  stages=[*stages, Stage("After", steps=[sh("true")])], post={"always": [sh("true")]})
    return convert(ir, "")["workflow"]["jobs"]


def scripts(stages, skipped=()):
    """The stages' scripts in Jenkins' order: a parallel stage's branches, then its post."""
    out = []
    for st in stages:
        if st.parallel:
            out += [s.args[0] for br in st.parallel if br.name not in skipped for s in br.steps]
            out += [s.args[0] for s in st.post.get("always", [])] if st.name not in skipped else []
        elif st.name not in skipped:
            out += [s.args[0] for s in st.steps]
    return out


def check(tmp_path, stages, initial=None, skipped_jobs=(), skipped_stages=(), checkout=True, act=False):
    """The post job's workspace (and After's, when it is a job of its own: after a parallel stage) is Jenkins'
    workspace after every stage. `act`: every job starts with the repository's files, as act copies them in."""
    init = build(tmp_path / "initial", initial or {})
    jobs = jobs_of(stages, checkout)
    if len(jobs) == 1:
        return {}  # every stage in one job: nothing is handed on
    starts = simulate(jobs, init, set(skipped_jobs), prepopulated=act)
    # skipDefaultCheckout: Jenkins' workspace starts empty
    expected = jenkins(scripts(stages, skipped_stages), init if checkout else build(tmp_path / "empty", {}))
    assert starts["post"] == expected
    if "after" in starts:
        assert starts["after"] == expected
    return starts["post"]


def par(name, *branches, post=None):
    return Stage(name, parallel=[Stage(f"{name}{chr(97 + i)}", steps=[sh(b)]) for i, b in enumerate(branches)],
                 post={"always": [sh(post)]} if post else {})


# ------------------------------------------------------------------------------------------- the review's findings
def test_consecutive_parallel_stages_merge_onto_the_snapshot_the_branches_started_from(tmp_path):
    """Finding 2: C and D start from the merge of A and B, not from B's snapshot. A creates a file, C changes it, D
    leaves it alone: After has C's version."""
    ws = check(tmp_path, [Stage("Build", steps=[sh("echo built > app")]),
                          par("P", "mkdir gen && echo one > gen/data", "echo b > b"),
                          par("Q", "echo two > gen/data", "echo d > d")])
    assert ws["gen/data"][2] == b"two\n"


def test_a_parallel_first_stage_merges_onto_the_checkout(tmp_path):
    """Finding 3: no job hands a workspace to the first fan-out, only the checkout. A edits a checked-out file, B leaves
    it alone: B's untouched copy does not win."""
    ws = check(tmp_path, [par("P", "echo edited >> README", "echo b > b")], initial={"README": "hello\n"})
    assert ws["README"][2] == b"hello\nedited\n"


@pytest.mark.parametrize("first", [True, False], ids=["first-branch", "later-branch"])
def test_directory_removals_mode_changes_and_type_changes_are_merged(tmp_path, first):
    """Finding 4: a removed directory is gone (not left empty), a directory's mode change is kept; type changes and
    new empty directories too. The first branch's workspace is taken whole, a later branch's changes are replayed:
    both are checked."""
    def fan(name, changes, other):
        return par(name, changes, other) if first else par(name, other, changes)
    ws = check(tmp_path, [
        Stage("Build", steps=[sh("mkdir -p old/sub keep f2d && echo x > old/sub/f && echo y > d2f && echo z > f2d/in && "
                                 "echo 'echo tool' > tool.sh")]),
        fan("P", "rm -r old && chmod 700 keep && mkdir empty && chmod +x tool.sh", "rm d2f && mkdir d2f && echo n > d2f/n"),
        fan("Q", "rm -r f2d && echo now-a-file > f2d", "echo q > q")])
    assert "old" not in ws and ws["keep"] == ("d", "0o700") and ws["empty"][0] == "d" and ws["tool.sh"][1] == "0o755"
    assert ws["d2f"][0] == "d" and ws["f2d"][0] == "f"


def test_read_only_directories_are_handed_on_and_merged(tmp_path):
    """A Go module cache is read-only: replaying another branch's changes into and out of it still works."""
    ws = check(tmp_path, [
        Stage("Build", steps=[sh("mkdir -p cache/mod && echo m > cache/mod/a && chmod -R a-w cache")]),
        par("P", "mkdir -p ro/x && echo r > ro/x/f && chmod -R a-w ro",
            "chmod u+w cache/mod && echo b > cache/mod/b && rm cache/mod/a && chmod u-w cache/mod")])
    assert ws["ro/x"][1] == ws["cache/mod"][1] == "0o555" and "cache/mod/a" not in ws


def test_names_with_spaces_newlines_and_leading_dashes(tmp_path):
    check(tmp_path, [par("P", "echo b > b",
                         "mkdir 'sp ace' && echo s > 'sp ace/f g' && echo n > $'nl\\nname' && echo d > ./-dash && "
                         "echo k > 'back\\slash' && echo l > 'lit\\nname' && echo p > '%s*[x]'")])


def test_symlinks_are_merged_as_links(tmp_path):
    ws = check(tmp_path, [Stage("Build", steps=[sh("echo a > a && ln -s a link && mkdir d && ln -s ../a d/up")]),
                          par("P", "ln -sfn missing link", "rm d/up && ln -s d dirlink")])
    assert ws["link"] == ("l", "missing") and ws["dirlink"] == ("l", "d") and "d/up" not in ws


def test_files_removed_earlier_do_not_come_back_from_the_jobs_own_checkout(tmp_path):
    """act copies the repository into every job: a restored workspace replaces those files, so a checked-out file an
    earlier stage removed stays removed."""
    check(tmp_path, [Stage("Clean", steps=[sh("rm README && echo built > app")]), par("P", "true", "echo b > b")],
          initial={"README": "hello\n"}, act=True)


def test_a_parallel_stage_post_job_hands_on_the_merged_workspace(tmp_path):
    check(tmp_path, [par("P", "echo a > a", "echo b > b", post="cat a b > ab"), par("Q", "rm ab", "echo q > q")])


# ---------------------------------------------------------------------------------------------- skipped producers
def test_a_skipped_parallel_stage_falls_back_to_the_workspace_before_it(tmp_path):
    stages = [Stage("Build", steps=[sh("echo built > app")]), par("P", "echo a > a", "echo b > b"),
              Stage("Pack", steps=[sh("echo pack >> app")])]
    check(tmp_path, stages, skipped_jobs={"p-pa", "p-pb"}, skipped_stages={"Pa", "Pb"})


def test_a_skipped_first_fan_out_falls_back_to_the_checkout(tmp_path):
    check(tmp_path, [par("P", "echo a > a", "echo b > b"), Stage("Pack", steps=[sh("cat README > r")])],
          initial={"README": "hello\n"}, skipped_jobs={"p-pa", "p-pb"}, skipped_stages={"Pa", "Pb"})


def test_one_skipped_branch_contributes_nothing(tmp_path):
    check(tmp_path, [Stage("Build", steps=[sh("echo x > x")]), par("P", "echo a > a", "echo b > b", "rm x")],
          skipped_jobs={"p-pb"}, skipped_stages={"Pb"})


# ------------------------------------------------------------------------------- conflicts: the later branch wins
@pytest.mark.parametrize("a, b", [
    ("echo A > f", "echo B > f"),
    ("rm f", "echo B > f"),
    ("echo A > f", "rm f"),
    ("echo A > d/new", "rm -r d"),
    ("chmod 600 f", "chmod 755 f"),
], ids=["write-write", "remove-write", "write-remove", "add-into-removed-dir", "mode-mode"])
def test_a_path_two_branches_change_takes_the_later_branchs_version(tmp_path, a, b):
    """Jenkins' result depends on timing; the converted merge takes the later branch (job order), which is what
    running the branches one after the other gives."""
    check(tmp_path, [Stage("Build", steps=[sh("echo base > f && mkdir d && echo x > d/x")]), par("P", a, b)])


@pytest.mark.parametrize("earlier", ["rm -r d", "rm -r d && echo file > d"], ids=["removed", "replaced-by-a-file"])
def test_a_later_branch_writing_into_a_directory_an_earlier_one_removed_gets_it_back(tmp_path, earlier):
    """Run one after the other, the later branch's write would fail; the merge gives the path to the later branch:
    the directory comes back with that branch's mode, holding only what that branch wrote into it."""
    jobs = jobs_of([Stage("Build", steps=[sh("mkdir d && chmod 700 d && echo x > d/x")]), par("P", earlier, "echo y > d/y")])
    ws = simulate(jobs, build(tmp_path / "initial", {}))["post"]
    assert {p: v for p, v in ws.items() if p.startswith("d")} == {"d": ("d", "0o700"), "d/y": ("f", "0o644", b"y\n")}


# ------------------------------------------------------------------------------------------- unsupported: loudly
def test_a_branch_without_a_change_list_fails_the_merge(tmp_path):
    jobs = jobs_of([Stage("Build", steps=[sh("true")]), par("P", "echo a > a", "echo b > b")])
    jobs["p-pb"]["steps"] = [s for s in jobs["p-pb"]["steps"] if s.get("name") != "Record the starting workspace"]
    with pytest.raises(StepFailed, match="has no change list"):
        simulate(jobs, build(tmp_path / "initial", {}))


def test_an_unreadable_directory_fails_the_hand_on(tmp_path):
    """A directory its owner cannot enter cannot be archived: the job fails, it does not hand on less."""
    jobs = jobs_of([Stage("Build", steps=[sh("mkdir -p locked/in && chmod 600 locked")]), par("P", "true", "true")])
    with pytest.raises(StepFailed, match="Hand on the pipeline workspace"):
        simulate(jobs, build(tmp_path / "initial", {}))


def test_concurrent_producers_must_start_from_the_same_snapshot():
    order = ["a", "b", "x", "y"]
    needs = {"a": [], "b": [], "x": ["a"], "y": ["b"]}  # x and y run concurrently but start from a and from b
    with pytest.raises(ValueError, match="start from different workspaces"):
        workspace.plan(order, needs, {"a", "b", "x", "y"}, {"x", "y"})


# --------------------------------------------------------------------------- hard links (third review of Phase 4)
def test_a_new_link_to_a_file_the_branch_did_not_change_stays_a_link(tmp_path):
    """The review's case: the merge extracted `linked` without `original` and failed. The new name changes the file's
    link count, so both names are replayed together, as one file."""
    ws = check(tmp_path, [Stage("Build", steps=[sh("echo content > original")]),
                          par("P", "echo a > a", "ln original linked")])
    assert ws["linked"] == ws["original"] == ("f", "0o644", b"content\n", ("linked", "original"))


def test_a_renamed_hard_link_stays_a_link(tmp_path):
    """Fourth review: `mv old linked` keeps the link count, so `original` looked unchanged and the merge could not
    link `linked` to it. A changed file's change list entry now takes its whole link group along."""
    ws = check(tmp_path, [Stage("Build", steps=[sh("echo content > original && ln original old")]),
                          par("P", "echo a > a", "mv old linked")])
    assert "old" not in ws and ws["linked"] == ws["original"] == ("f", "0o644", b"content\n", ("linked", "original"))


@pytest.mark.parametrize("change", ["rm p2", "echo more >> p1", "mkdir d && ln original d/third && ln p1 d/p3",
                                    "mkdir e && mv p2 e/p2", "mv p1 p1.new && ln p1.new p1.second"],
                         ids=["link-removed", "linked-file-changed", "links-in-a-new-directory", "link-moved",
                              "renamed-then-linked"])
def test_hard_links_are_merged_as_links(tmp_path, change):
    """Compared with Jenkins' workspace including which paths are one file (`tree` records hard-link groups)."""
    check(tmp_path, [Stage("Build", steps=[sh("echo content > original && echo pair > p1 && ln p1 p2")]),
                     par("P", "echo a > a", change)])


# -------------------------------------------------------------- transfer failures (third review of Phase 4)
def fan_jobs():
    return jobs_of([Stage("Build", steps=[sh("echo built > app")]), par("P", "echo a > a", "echo b > b")])


@pytest.mark.parametrize("fault, error", [("lost", "did not arrive"), ("corrupt", "tar|gzip"),
                                          ("incomplete", "has no change list")])
def test_a_workspace_that_did_not_arrive_intact_fails_the_merge(tmp_path, fault, error):
    """B ran and uploaded, but its workspace is missing (a failed download, an expired artifact), truncated, or came
    without its change list: the merge fails instead of restoring the workspace without B's changes."""
    with pytest.raises(StepFailed, match=error):
        simulate(fan_jobs(), build(tmp_path / "initial", {}), **{fault: {"p-pb"}})


def test_a_skipped_job_is_not_a_lost_workspace(tmp_path):
    """The same missing workspace from a job that was skipped is the normal fallback: no error."""
    starts = simulate(fan_jobs(), build(tmp_path / "initial", {}), {"p-pb"})
    assert "a" in starts["post"] and "b" not in starts["post"]


def test_a_lost_workspace_reached_through_an_approval_job_is_restored_with_a_warning(tmp_path):
    """The branches need only the approval job, which restores nothing: Build's result is not known to them, so a
    skipped and a lost workspace look the same. The fallback is restored and the merge step says so."""
    jobs = jobs_of([Stage("Build", steps=[sh("echo built > app")]),
                    Stage("Deploy", input={"message": "ok?"},
                          parallel=[Stage("Da", steps=[sh("true")]), Stage("Db", steps=[sh("true")])])],
                   checkout=False)
    assert jobs["deploy-da"]["needs"] == "deploy-input"
    logs: dict = {}
    starts = simulate(jobs, build(tmp_path / "initial", {}), lost={"build"}, logs=logs)
    assert "app" not in starts["deploy-da"]
    assert any("::warning::the workspace of job 'build' did not arrive and its result is not known here" in line
               for line in logs["deploy-da"])


# ------------------------------------------- transfer faults combined with skipped jobs (fourth review of Phase 4)
GATED = [Stage("Build", steps=[sh("echo built > app")]),
         Stage("Gate", input={"message": "ok?"}, when=When(conditions=[Condition("expression", "false")],
                                                             before_input=True), steps=[sh("echo g > g")])]


def test_a_lost_fallback_behind_a_skipped_job_is_not_silent(tmp_path):
    """The review's case: Gate is skipped, so Pack falls back to Build's workspace, and only that download fails.
    Build is not a job Pack needs, so its result is not known to Pack: the merge step says it is taking Build as
    skipped, instead of quietly restoring nothing."""
    jobs = jobs_of([*GATED, Stage("Pack", steps=[sh("true")])], checkout=False)
    assert jobs["pack"]["needs"] == "gate"
    logs: dict = {}
    starts = simulate(jobs, build(tmp_path / "initial", {}), {"gate"}, lost={"pack:build"}, logs=logs)
    assert "app" not in starts["pack"]
    assert any("::warning::the workspace of job 'build' did not arrive" in line for line in logs["pack"])
    # the gate job fetched Build's workspace without a fault: no warning there
    assert not any("::warning::" in line for line in logs["gate-gate"])


def test_a_lost_fallback_whose_job_is_known_to_have_run_fails_the_merge(tmp_path):
    """The post job needs every job: Build's result is known (it ran), so its missing workspace behind the skipped
    Gate is refused, not replaced by an older one."""
    ir = Pipeline(dialect="declarative", agent=Agent("any"), options={"skipDefaultCheckout": True}, stages=GATED,
                  post={"always": [sh("true")]})
    jobs = convert(ir, "")["workflow"]["jobs"]
    with pytest.raises(StepFailed, match="job 'build' ran \\(success\\) but its workspace did not arrive"):
        simulate(jobs, build(tmp_path / "initial", {}), {"gate"}, lost={"post:build"})


def test_a_skipped_job_and_its_fallback_arriving_restore_jenkins_workspace(tmp_path):
    check(tmp_path, [*GATED, Stage("Pack", steps=[sh("cat app > packed")])], skipped_jobs={"gate"},
          skipped_stages={"Gate"}, checkout=False)


# ------------------------------------------------------------------- seeded combinations of shapes and changes
ZONES = ["z0", "z1", "z2", "z3", "z4", "z5"]
INITIAL = {"z0/a": "a0\n", "z0/d/x": "x0\n", "z1/a": ("run\n", 0o755), "z1/l": ("->", "a"), "z2/d/e/y": "y\n",
           "README": "hello\n"}


def change(rng: random.Random, zone: str, k: int) -> str:
    """One change inside a zone; tolerant of the zone's current state (both sides see the same state)."""
    z = zone
    return rng.choice([
        f"mkdir -p {z}/d/e 2>/dev/null && printf %s v{k} > {z}/{rng.choice(['a', 'b', 'd/x', 'd/e/y'])} || true",
        f"[ -f {z}/a ] && printf + >> {z}/a || true",
        f"rm -rf {z}/{rng.choice(['a', 'b', 'd', 'd/x', 'd/e'])}",
        f"f={z}/{rng.choice(['a', 'd/x'])}; [ -f $f ] && chmod {rng.choice(['600', '644', '700', '755'])} $f || true",
        f"chmod {rng.choice(['700', '750', '755'])} {z}/{rng.choice(['d', 'd/e'])} 2>/dev/null || true",
        f"mkdir -p {z} && rm -rf {z}/l && ln -s {rng.choice(['a', 'd', 'missing'])} {z}/l",
        f"rm -rf {z}/a && mkdir -p {z}/a/in && printf f > {z}/a/in/f",
        f"rm -rf {z}/d && mkdir -p {z} && printf file > {z}/d",
        f"mkdir -p {z}/empty{k}",
        f"mkdir -p '{z}/sp ace' && printf s > '{z}/sp ace/f {k}'",
        f"mkdir -p {z}/ro{k}/in && printf r > {z}/ro{k}/in/f && chmod -R a-w {z}/ro{k}",
        f"[ -f {z}/a ] && ln -f {z}/a {z}/hl{k} || true",
        f"[ -f {z}/hl{k - 1} ] && rm -f {z}/hl{k - 1} || true",
        f"[ -f {z}/hl{k - 1} ] && mv -f {z}/hl{k - 1} {z}/mv{k} || true",
    ])


def scenario(seed: int) -> list[Stage]:
    rng = random.Random(seed)
    stages, k = [], 0

    def changes(zones):
        nonlocal k
        out = []
        for _ in range(rng.randint(1, 3)):
            k += 1
            out.append(change(rng, rng.choice(zones), k))
        return " ; ".join(out) if zones else "true"

    for level in range(rng.randint(2, 4)):
        if rng.random() < 0.6:
            n = rng.randint(2, 3)
            zones = rng.sample(ZONES, n * 2)
            branches = [changes(zones[2 * i:2 * i + 2]) for i in range(n)]
            post = changes(ZONES) if rng.random() < 0.3 else None
            stages.append(par(f"P{level}", *branches, post=post))
        else:
            stages.append(Stage(f"S{level}", steps=[sh(changes(ZONES))]))
    return stages


@pytest.mark.parametrize("seed", range(24))
def test_seeded_pipelines_restore_jenkins_workspace(tmp_path, seed):
    check(tmp_path, scenario(seed), initial=INITIAL, checkout=seed % 3 != 0, act=seed % 3 == 1)


@pytest.mark.parametrize("fault", ["lost", "corrupt", "incomplete"])
@pytest.mark.parametrize("seed", range(12))
def test_seeded_transfer_faults_fail_loudly_or_change_nothing(tmp_path, seed, fault):
    """One handed-on workspace of a seeded pipeline is lost, truncated or arrives without its change list: the run
    fails loudly, warns, or ends with Jenkins' workspace anyway (the workspace was only a fallback, or the first of a
    merge, which needs no change list). Never a silently different workspace."""
    stages, checkout = scenario(seed), seed % 3 != 0
    jobs = jobs_of(stages, checkout)
    uploads = sorted(jid for jid, job in jobs.items() for st in job["steps"]
                     if st.get("uses", "").startswith("actions/upload-artifact")
                     and st["with"]["name"] == f"j2gha-ws-{jid}")
    if not uploads:
        return
    victim = random.Random(seed).choice(uploads)
    init = build(tmp_path / "initial", INITIAL)
    logs: dict = {}
    try:
        starts = simulate(jobs, init, logs=logs, **{fault: {victim}})
    except StepFailed as e:
        assert "::error::" in str(e) or "tar:" in str(e) or "gzip:" in str(e), str(e)
        return
    expected = jenkins(scripts(stages), init if checkout else build(tmp_path / "empty", {}))
    warned = any("::warning::" in line for lines in logs.values() for line in lines)
    assert starts["post"] == expected or warned


@pytest.mark.parametrize("seed", range(32))
def test_seeded_skipped_stages_with_a_lost_fetch_fail_loudly_or_change_nothing(tmp_path, seed):
    """A parallel stage is skipped (a gate said no) *and* one download of one consumer fails: the fallback chain the
    merge relies on is checked, so the run fails, warns, or ends with Jenkins' workspace without the skipped stage."""
    rng = random.Random(1000 + seed)
    stages, checkout = scenario(seed), seed % 3 != 0
    fans = [st for st in stages if st.parallel]
    if not fans:
        return
    skip = rng.choice(fans)
    skipped_jobs = {f"{skip.name.lower()}-{br.name.lower()}" for br in skip.parallel} | {f"{skip.name.lower()}-post"}
    jobs = jobs_of(stages, checkout)

    def needs(job):
        n = job.get("needs") or []
        return {n} if isinstance(n, str) else set(n)

    # the fallback downloads of the jobs right after the skipped stage, of producers that ran: the chain the skip
    # makes the merge rely on (the post job needs every job, so it knows their results: tested apart)
    fetches = sorted(f"{jid}:{st['with']['name'].removeprefix('j2gha-ws-')}" for jid, job in jobs.items()
                     if jid not in skipped_jobs | {"post"} and needs(job) & skipped_jobs for st in job["steps"]
                     if st.get("uses", "").startswith("actions/download-artifact") and "if" in st
                     and st["with"]["name"].startswith("j2gha-ws-")
                     and st["with"]["name"].removeprefix("j2gha-ws-") not in skipped_jobs)
    if not fetches:
        return
    lost = rng.choice(fetches)
    init = build(tmp_path / "initial", INITIAL)
    logs: dict = {}
    try:
        starts = simulate(jobs, init, skipped_jobs, lost={lost}, logs=logs)
    except StepFailed as e:
        assert "::error::" in str(e), str(e)
        return
    skipped_stages = {br.name for br in skip.parallel} | {skip.name}
    expected = jenkins(scripts(stages, skipped_stages), init if checkout else build(tmp_path / "empty", {}))
    warned = any("::warning::" in line for lines in logs.values() for line in lines)
    assert starts["post"] == expected or warned, lost
