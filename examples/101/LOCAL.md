# Example 101: local twin of example 001

Derived from [example 001](../001/README.md) (apache/couchdb, `build-aux/Jenkinsfile` at `d072d90`). The original is
kept verbatim in `examples/001/`; this copy is edited only as far as needed for the pipeline to run to completion in
the harness. Every edit is marked `// j2gha-local:` / `# j2gha-local:` in the Jenkinsfile. Line numbers below are the
original's, with the twin's in brackets where they differ.

| Line | Original | Edit | Why | Feature kept? |
|---|---|---|---|---|
| 46-283 (46-62) | `meta = [ ... ]`: 13 live platforms (centos8, centos9, centos10, jammy, noble, resolute, base, base-max-erlang, base-intermediate-erlang, base-quickjs, base-arm64, bookworm, win2022) and commented-out ppc64le, s390x, FreeBSD and macOS entries | the single `'base'` entry (Debian x86_64), kept exactly as it was, behind a comment naming what was cut | the map is the fan-out of the dynamic `parallel`: every entry pulls a CentOS/Ubuntu/Debian CI image with Erlang, and `base-arm64`/`win2022` need an ARM64 Docker host (`docker-arm64` label) and a Windows node (`win`, PowerShell, couchdb-glazier). One Linux entry gives the parallel one branch that can run here | yes: `collectEntries` → `parallel`, `generateContainerStage` with nested scripted stages, try/catch/finally, `retry`, `timeout`, `junit`, stash/unstash and archive all run; `generateNativeStage` (the macOS/FreeBSD/Windows path) stays in the file but no entry selects it, as before for the commented-out ones |
| 518 (297) | `docker.image(meta[platform].image).inside("${DOCKER_ARGS}") {` | `withDockerContainer(image: meta[platform].image, args: "${DOCKER_ARGS}") {` | the `docker` global's `inside()` runs `sh 'docker inspect -f . <image>'` and, when that fails, `sh 'docker pull <image>'` *for real* before it enters `withDockerContainer` (docker-workflow `Docker.groovy`, `Image.inside`/`pull`); with a client but no daemon the pull fails and the stage aborts. `withDockerContainer` is the step `inside()` ends in, and the harness stubs it in both modes (the body runs on the built-in node) | the container wrapper around build & test is kept as its underlying step; `docker.withRegistry('https://docker.io/', 'dockerhub_creds')` is unchanged (it calls `withDockerRegistry`, stubbed) |
| 566 (345) | `cd ${platform} && git clone https://github.com/apache/couchdb-pkg` | `cd ${platform} && mkdir -p couchdb-pkg` | couchdb-pkg's Makefile needs dpkg-buildpackage, rpmbuild and Erlang; the directory is all the next `dir()` needs | the `dir("${platform}/couchdb-pkg")` block and the step label are unchanged |
| 568 (347) | `make --output-sync=target` (inside couchdb-pkg) | `echo "..." > ../couchdb/couchdb_3.5.2_amd64.deb` | builds the distribution packages; the stand-in writes the `.deb` where the unchanged *Stage package artifacts* step looks (`${platform}/couchdb/*.deb` → `pkgs/base/`), which `archiveArtifacts 'pkgs/**'` then archives | yes |
| 704 (483) | `./configure --spidermonkey-version 128 --with-nouveau` | `echo "skipped: ..."` | `configure` runs `erl` at its line 39 (the 001 full run: `./configure: 39: erl: not found`) | one `sh` step per original step, so the trace has the same shape |
| 705-707 (484-486) | `make erlfmt-check`, `make elixir-source-checks`, `make python-black` | `echo "skipped: ..."` ×3 | need Erlang and erlfmt, Elixir, and black | same |
| 708 (487-508) | `make -j4 --output-sync=target dist` | a shell block that builds `apache-couchdb-3.5.2.tar.gz` (name from `version.mk`) holding LICENSE, NOTICE, version.mk, a `configure` script that prints its arguments, an `eunit-report.xml` with two cases and a `Makefile` whose targets (`all xref elixir elixir-search mango-test weatherreport-test nouveau-test quickjs-test262 build-report`) print, and whose `eunit` copies the report to `.eunit/couch_tests.xml` | `make dist` needs Erlang, rebar, Elixir and Sphinx. The stand-in gives the pipeline the one file it stashes and archives, and a `configure`/`Makefile` that answer every command the *Test and Package* stage runs. The name is the tarball-build form of CouchDB's `COUCHDB_VERSION` (`vsn_major.vsn_minor.vsn_patch`); the git-checkout form appends the HEAD short sha, which would differ between the Jenkins checkout (`d072d90`) and the harness run branch on GHA | the `post success` stash and archive, the `unstash`, `tar -xf --strip-components=1`, `sh "${configure(meta[platform])}"`, every `make` target with its `retry`/`timeout`, `writeFile`, the `junit '**/.eunit/*.xml, ...'` pattern and `wscleanup()` run unchanged against the stand-in |

Unchanged: the script-level globals (`DOCKER_IMAGE_BASE`, the Erlang versions, `docs_changed`/`github_changed`/
`other_changes` with `${env.CHANGE_TARGET}`), `containerClouseauConfig`, `configure()`, `wscleanup()`, the whole
`pipeline {}` apart from the five *Build Release Tarball* steps: `agent none`, `environment` (`DOCKER_ARGS` with its
host mounts), `options` (`buildDiscarder` is removed by the localiser; `preserveStashes`, `timeout`, `timestamps`
stay), the three `docker { ... registryCredentialsId 'dockerhub_creds' }` agents (localised to the built-in node by the
harness), *Setup Env*'s `script {}` with its four `env.X` assignments and two `sh(returnStatus: true)` conditions,
*Build Docs* (its `when` is false on the default branch, so its `make python-black`/docs commands are left as they
are), `when { beforeOptions true; expression { ... } }` on three stages, every `post` section, and *Test and Package*
with its `collectEntries`/`parallel`.

**What this twin tests.** A Declarative pipeline whose last stage is a scripted dynamic parallel built from a map
(`meta.collectEntries` → `parallel`), with `docker.withRegistry` and a container wrapper around nested scripted
stages, a stash handed from a Declarative `post success` into those scripted stages, `junit` on a hidden-directory
pattern, archives from two different stages, `wscleanup()` between stages in one workspace, and `when { beforeOptions
true }` gates on env variables that a `script {}` in the first stage sets. On the default branch `CHANGE_TARGET` is
unset, so each `git diff --name-only origin/null | grep -q ...` exits 1 (git fails, grep sees no input; the 001 full
run shows the `fatal: ambiguous argument 'origin/null'` lines), every flag stays `'0'`, *Build Docs* is skipped and
*Build Release Tarball* and *Test and Package* run: the full build path.

Expected on Jenkins: **SUCCESS**; stages Setup Env, Build Docs (skipped), Build Release Tarball, Test and Package →
`base` → `Debian x86_64 - build & test`, `Debian x86_64 - package`; archived `apache-couchdb-3.5.2.tar.gz` and
`pkgs/base/couchdb_3.5.2_amd64.deb`; JUnit 2 cases (`couch_tests.basic`, `couch_tests.config`). The run clones
couchdb twice (Setup Env and Build Release Tarball; the scripted `node` does no checkout) and `wscleanup()` empties
the built-in node's workspace between stages, as the real pipeline does inside its containers.

Expected on the converted side: **differs**, for three independent reasons, all in the converter (the twin's purpose
is the Jenkins reference):

1. **Hard gate `DynamicParallel`** (line 540): the `test-and-package` job holds only the stage-entry step and the
   `script {}`/`parallel` placeholders; nothing from `generateContainerStage` is emitted (no unstash, make, junit or
   package archive), so the GHA trace has none of the `base` stages.
2. **Script-set env gates**: `env.DOCS_CHANGED = '0'` and the three other assignments, and the two
   `if (sh(returnStatus: true, ...) == 0)` conditions, are manual placeholders in `setup-env`; nothing writes
   `ONLY_DOCS_CHANGED`/`ONLY_GITHUB_CHANGED` (and `$GITHUB_ENV` would not cross jobs anyway). The stage-entry
   conditions `env.ONLY_DOCS_CHANGED == '0' && env.ONLY_GITHUB_CHANGED == '0'` compare an unset variable with `'0'`,
   so on GHA *Build Release Tarball* and *Test and Package* are **skipped** (*Build Docs*, gated on `== '1'`, is
   skipped on both sides): Jenkins takes the full build path, the converted workflow takes none and succeeds
   vacuously (no stash, no tarball archive). This is
   the same `script {}` variable gap 106 states, here on `when` gates rather than on a command.
3. **Job containers** (C12): full-mode variants keep `container:`; `setup-env`, `build-docs` and
   `build-release-tarball` carry the literal `image: ${DOCKER_IMAGE_BASE}-${MINIMUM_ERLANG_VERSION}` (the
   script-level globals are not resolved, reported ✅ mapped), which act and the runner cannot pull, so those jobs
   fail at container creation before any step. Trace variants drop containers, so there the jobs run and reason 2
   applies.

Also: the three `${J2GHA_TODO_wscleanup__}` run steps (C4) expand to nothing in bash and exit 0; `CHANGE_TARGET` is
emitted as `${{ github.base_ref }}` and the `git diff` strings are inside placeholders, so the C2 null-vs-empty
difference does not arise. Outputs: Jenkins 2 archived files and 2 JUnit cases against none on GHA.

Scenario: `uv run j2gha run 101 --tier jenkins,act --mode full` (default branch `main`, no parameters).

`uv run j2gha analyze 101 && uv run j2gha convert 101 && uv run j2gha validate 101`: 4 jobs, automation 69.3%,
validation OK (actionlint 1 shellcheck info on the original `ls -l ${WORKSPACE}`; zizmor 3 `unpinned-images` on the
literal container image; policy: 2 manual placeholders, 3 `unresolved-groovy` warnings for `wscleanup()`). The
Declarative cross-check inside `analyze` was skipped at creation time because the controller was in use.

Result (2026-10-10, Jenkins full vs act full): Jenkins **SUCCESS**, act **failure** at *-*, verdict **differs**; JUnit cases 2 (Jenkins) / 0 (act), differs; archived files 2 (Jenkins) / 0 (act), differs. The dynamic `parallel` is not converted (hard gate) and the `when` gates compare env values that only the manual `script {}` placeholders would set, so the converted build stages are skipped and the docker-agent jobs keep literal container images; the Jenkins reference (one platform) succeeds with the release tarball and package archived and 2 JUnit cases.
