# Example 114: local twin of example 014

Derived from [example 014](../014/README.md) (The-OpenROAD-Project/OpenLane, `Jenkinsfile` at `32dc185`, default
branch `superstable`). The original is kept verbatim in `examples/014/`; this copy is edited only as far as needed for
the pipeline to run to completion in the harness. Every edited line carries `// j2gha-local:` in the Jenkinsfile.
Line numbers are the original file's.

The original builds the OpenROAD and OpenLane Docker images (multi-GB, hours), saves the image to a tarball, stashes
it, and in each of 22 matrix cells installs a PDK through pip/volare (GB), loads the image and runs the RTL-to-GDS
flow for one design. None of that is possible without a Docker daemon. The twin keeps the two Python helper scripts
(they run for real now that `python3-yaml` is installed), the stash/unstash of `openlane-current.tar.gz` (a small
gzip instead of the image), the `retry(3)`/try/catch/`sleep` structure, the 22-cell matrix, the dynamic
`stage("${DESIGN} - ...")` blocks, the `sed` on `tool_metadata.yml`, both `post` blocks, and the explicit
`GitSCM` checkout of OpenROAD into `openroad/`.

| Line | Original | Edit | Why | Feature kept? |
|---|---|---|---|---|
| 30 | `python3 .github/scripts/update_tools.py openroad_app` | (unchanged) | needs only PyYAML, `git remote get-url origin`, and `git ls-remote` of the public OpenROAD repository (GitHub, no token); rewrites `dependencies/tool_metadata.yml` to the latest OpenROAD commit | a real script runs on both sides |
| 31 | `make -C docker build-openroad_app` | `echo make -C docker build-openroad_app` | builds the OpenROAD image; no Docker daemon | the `sh` step inside `retry`/try |
| 32 | `NEW_SHA = sh(returnStdout: ..., "python3 dependencies/tool.py -f commit openroad_app")` | (unchanged) | reads the vendored `includedyaml` and `tool_metadata.yml`; no network | a real captured-output script |
| 33 | `make -C docker openlane OPENLANE_IMAGE_NAME=current:latest` | `echo make -C docker openlane ...` | builds the OpenLane image; no Docker daemon | - |
| 34 | `docker save current:latest-amd64 \| gzip > openlane-current.tar.gz` | `echo "docker save current:latest-amd64 (j2gha-local stand-in for the image)" \| gzip > openlane-current.tar.gz` | no image to save; a small gzip keeps the stash real | `stash name: 'data', includes: 'openlane-current.tar.gz'` is unchanged |
| 81-82 | `python3 -m pip install --user --upgrade --no-cache-dir pip` / `volare` | `echo python3 -m pip ...` | pip into the system Python is refused on Debian 13 (PEP 668) and only `make pdk` needs volare | the `${DESIGN} - Install PDK` stage and its three `sh` steps |
| 83 | `make pdk` | `echo make pdk` | downloads a PDK (GB) through volare | - |
| 87 | `docker load --input openlane-current.tar.gz` | `echo docker load --input openlane-current.tar.gz && gzip -dc openlane-current.tar.gz` | no Docker daemon; decompressing the unstashed file proves it arrived intact | `unstash "data"` is unchanged |
| 90-91 | `OLD_SHA = sh(returnStdout: ...)`; `sed -i s/${OLD_SHA}/${NEW_SHA}/ ./dependencies/tool_metadata.yml` | (unchanged) | `tool.py` runs for real; on Jenkins `OLD_SHA` is the commit in the cell's fresh checkout and `NEW_SHA` the one found in the build stage, so the `sed` replaces it | the Groovy-variable hand-over between stages, the known gap |
| 94 | `make OPENLANE_IMAGE_NAME=current:latest TEST_DESIGN=${DESIGN} test` | `echo make ... TEST_DESIGN=${DESIGN} test` | runs the flow inside the image (no Docker daemon, hours per design) | the per-cell `sh` with the matrix value interpolated (including the quoted `-override_env` values) |

Unchanged: the file-level `NEW_SHA`/`OLD_SHA` variables, `agent any` on the pipeline and on the `Test` stage (each
cell gets its own node allocation and `Declarative: Checkout SCM`), `options { timeout(8h) }`, `environment
{ ROUTING_CORES }`, the OpenROAD `checkout([$class: "GitSCM", ... RelativeTargetDirectory 'openroad'])`, `retry(3)`,
the try/catch with `sleep(60)` and `sh 'exit 1'` (not reached when the body succeeds, so the happy path does not
sleep), the stash/unstash, the 22-value matrix, the four dynamic `stage("${DESIGN} - ...")` blocks, the cell
`post { failure { archiveArtifacts ... } }` and the pipeline `post { failure { emailext } }`.

What this twin tests that the original cannot: `retry` around try/catch on the happy path, a stash made in one stage
and unstashed in 22 matrix cells on their own agents, captured-output `sh` into script-level Groovy variables used
across stages, and the explicit second-repository checkout, all through to a green Jenkins run.

Expected differences on the converted side:

- **`sed -i s/${OLD_SHA}/${NEW_SHA}/` fails in every cell** (`sed: no previous regular expression`): the converter
  emits the two `sh(returnStdout:)` steps but does not carry their values into `OLD_SHA`/`NEW_SHA` (approximated
  items at lines 32 and 90, "captured output not propagated"), so the shell variables are empty on GHA. The cells
  fail at `${DESIGN} - Update OpenROAD commit`, the cell `post failure` archive finds no `designs/**/*.log` (the
  repository has none) and fails too, and the pipeline `post failure` emailext placeholder runs. Jenkins succeeds.
  This is the Groovy-variable gap already stated by example 106, reproduced here from `sh(returnStdout:)` rather than
  from `script {}` assignments; a *differs* verdict with Jenkins SUCCESS against a converted failure in `Run Tests` is
  the expected, real finding.
- C8: the OpenROAD `GitSCM` checkout is converted to a checkout of the current repository, so the converted run has
  no `openroad/` directory; nothing in the pipeline reads it, so this does not change the outcome.
- C9: `retry(3)` becomes a three-attempt loop around each `run` step (visible in the step bodies); on the happy path
  every step runs once on both sides, and the `sleep`/`exit 1` steps are skipped on GHA as the catch is not entered on
  Jenkins.
- `update_tools.py` takes the `GITHUB_ACTIONS=true` path on GHA (writes `NO_UPDATE` to `$GITHUB_ENV`) and the local
  path on Jenkins (`git remote get-url origin`, prints the value); the same `git ls-remote` runs on both.
- The 22 cells each restore the hand-off workspace and download the stash; under act this is the same fan-out that lost
  jobs to act's `docker cp` fault in example 109, so the self-hosted tier is the evidence for this twin.

Scenario: `uv run j2gha run 114 --tier jenkins,act --mode full --branch superstable` (the repository's default
branch; no `when` conditions). The Jenkins run clones OpenLane once for the pipeline and once per cell (22 cells over
16 executors), plus one clone of OpenROAD (about 2 minutes); `git ls-remote` of OpenROAD runs in the build stage.

Note: `analyze` was run while the controller was busy, so Jenkins' own Declarative validation (`toJson`) of the twin
has not been cross-checked yet; the Groovy AST parse succeeded.

Result (2026-10-10, Jenkins full vs act full): Jenkins **SUCCESS**, act **failure** at *${DESIGN} - Update OpenROAD commit*, verdict **differs**. The converted matrix cells fail at *Update OpenROAD commit* because `OLD_SHA`/`NEW_SHA` come from `sh(returnStdout:)` and are not carried over (the Groovy-variable gap), so their `sed` exits 1; the Jenkins reference succeeds across all 22 cells (a first attempt lost 3 cells to 10-minute clone timeouts under 22 concurrent fresh clones).
