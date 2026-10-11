# Example 103: local twin of example 003

Derived from [example 003](../003/README.md) (frankarobotics/franka_description, `Jenkinsfile` at `37c4be2`). The
original is kept verbatim in `examples/003/`; this copy is edited only as far as needed for the pipeline to run to
completion in the harness. Every edit is marked `// j2gha-local:` / `# j2gha-local:` in the Jenkinsfile. Line numbers
are the same in both files except the last row (the twin is four lines shorter from line 256 on).

| Line | Original | Edit | Why | Feature kept? |
|---|---|---|---|---|
| 65 | `sh '.ci/run_urdf_tests.sh'` | `sh 'echo "skipped: .ci/run_urdf_tests.sh (...)"'` | the script sources `/opt/ros/jazzy/setup.sh` and runs `colcon build`/`colcon test` on the package; ROS 2 comes from the stage's `dockerfile` agent (`.docker/Dockerfile`), which the harness localises to the built-in node (the 003 full run failed here: `/opt/ros/jazzy/setup.sh: No such file or directory`). No ROS on either side | the stage, its `dockerfile { dir '.docker'; reuseNode true }` agent and its one `sh` step are kept; nothing later uses the stage's output |
| 80 | `sh "./scripts/create_urdf.sh --no-ee --no-prefix ${ROBOT}"` | `sh "mkdir -p urdfs && echo \"<robot name='${ROBOT}'/>\" > urdfs/${ROBOT}.urdf && echo ... > urdfs/${ROBOT}.srdf"` | `create_urdf.sh` is `docker build` of `.docker` followed by `docker run` of that image to run xacro (no daemon on either side; the image is a ROS desktop build). The stand-in writes, per cell, the two files that `stash name: "ROBOT_${ROBOT}_urdf", includes: "${ROBOT}.urdf"` and `..._srdf` take | yes: the 5-cell matrix, the GString `${ROBOT}` in a `sh`, `dir('urdfs')` and both stashes are unchanged |
| 102 | `sh "./scripts/create_urdf.sh --only-ee --robot-ee ${EE}"` | `sh "mkdir -p urdfs && echo \"<robot name='${EE}'/>\" > urdfs/${EE}.urdf"` | same script; writes the file `stash name: "EE_${EE}_urdf"` takes | yes: the 2-cell matrix and its stash |
| 252-259 (252-255) | `fpm -s tar -t deb -n "robot-descriptions" -v ${VERSION} -a all --vendor "..." --maintainer "..." "${ARTIFACT_FILENAME}_${VERSION}.tar.gz"` (one command over eight lines) | `tar czf "${ARTIFACT_FILENAME}_${VERSION}_all.deb" "${ARTIFACT_FILENAME}_${VERSION}.tar.gz"` behind three comment lines | fpm (a Ruby gem) is not installed. The stand-in writes a file under the name fpm would have produced, so the unchanged `mv` to `_all.ipk`, the `printf`/`sha1sum` line and `archiveArtifacts '*.tar.gz'` run as written | yes: the `dir('dist')`, the `tar czvf` of `usr/share`, the `.ipk` rename and the archive are unchanged |

Unchanged, and worth knowing: `@Library('fe-gitlab-pipeline-steps@lts-2.2') _` and the `FePipelineOptionDefaults`
import (removed and stubbed by the localiser; `gitLabConnection` and `buildDiscarder` are dropped with them);
`VERSION = feDetermineVersionFromGit()` (a library step: on Jenkins the stub makes `VERSION` the string `j2gha-stub`,
so the archive is `robot-descriptions_j2gha-stub.tar.gz`; the converted workflow sets `VERSION: 'TODO-j2gha:
feDetermineVersionFromGit()'`, so its archive name would differ. Left as it is because the converted archive job cannot
run anyway (below); set `VERSION = '0.0.0'` if that changes); the *Check Commit Message* script
(the cited commit's message, "[git-lab migration] post-migration updates (Jenkinsfiles, submodule URLs)", contains no
skip keyword); `notifyBitbucket()`; `git clean -x -d -f`; the two matrices; the `docker { image
'franka/build/ubuntu-24.04:0.27.0'; reuseNode true }` agent (localised to the built-in node); the nested stages, the
5-branch `parallel` with `dir`/`unstash`/`mv`; the mesh copies (`meshes/robots/{fp3,fr3,fr3v2,fr3v2_1,tmrv0_2}` and
`meshes/robot_ee/{cobot_pump,franka_hand_white}` exist upstream at the cited commit); `when { not { equals ...
currentBuild.result }; anyOf { buildingTag(); branch "${env.BRANCH_NAME}" } }`; `fePublishOpkg`/`fePublishBuildInfo`
(unknown steps, stubbed); the two downstream `build job:` steps (`FULL_MODE_STUBS`); `post always` with `cleanWs()` and
`feNotifySCM`.

**What this twin tests.** Two Declarative matrices that stash one file per cell, consumed by `unstash` in nested
stages and a five-branch `parallel` inside a stage with its own (docker) agent; a `dockerfile` agent with `reuseNode`;
`dir()` + `mv` into a distribution tree; an archive from inside `dir('dist')`; a `when` combining
`equals currentBuild.result`, `buildingTag()` and `branch`; two downstream `build` steps in parallel; and a pipeline
`post` with `cleanWs()`. With the stand-ins every `sh` is real on both sides, and the stashed files are real files.

Expected on Jenkins: **SUCCESS**, all 28 stages run (*Publish to artifactory* runs: `branch "main"` matches the
scenario's `BRANCH_NAME`, the two `fe*` steps are stubs; *humble*/*jazzy* run with the stubbed `build`); archived
`robot-descriptions_j2gha-stub.tar.gz` (one file, from `dist/`); no tests. Because `agent any` replaces the two
`reuseNode` agents, *Run URDF tests* and *Archive URDFs and SRDFs* get their own workspace (`@2`) with a fresh
checkout, where the real pipeline reuses the pipeline workspace; the archive stage needs only the checkout (meshes)
and the stashes, so the result is the same.

Expected on the converted side: **differs**, failing at *Run URDF tests*; the Jenkins reference is the twin's value.
In order of what the workflow would meet:

1. **`dockerfile` agent** → the `run-urdf-tests` job runs `docker build -t j2gha-agent:local -f .docker/Dockerfile
   .docker` and then the stage's step as `docker run ... j2gha-agent:local sh -c '...'`. act's job containers and the
   harness JIT runners have no Docker socket, so `docker build` fails ("Cannot connect to the Docker daemon") and
   every later job, which `needs` it, is skipped; only `check-commit-message` (Check Commit Message + Get Ready:
   `git log -1`, two manual placeholders, `git clean`) and `post` run. A GitHub-hosted runner has a daemon and would
   build the real ROS image (`osrf/ros:jazzy-desktop`, gigabytes) just to `echo`.
2. **Matrix stash names** (new conversion gap, also in 003's workflow): the cells' `upload-artifact` steps are named
   literally `stash-ROBOT_-ROBOT-_urdf`, `stash-ROBOT_-ROBOT-_srdf` and `stash-EE_-EE-_urdf` (the GString
   `ROBOT_${ROBOT}_urdf` is sanitised, not expanded per cell, though the file path does use `${{ env.ROBOT }}`),
   while the archive job downloads `stash-ROBOT_fr3_urdf` ... `stash-EE_franka_hand_urdf`. The five cells would
   overwrite one artifact (`overwrite: true`) and all twelve unstashes would fail with "Artifact not found", where
   Jenkins unstashes twelve files.
3. **Job container** `franka/build/ubuntu-24.04:0.27.0` on `archive-urdfs-and-srdfs` (kept by the full-mode
   variants): a private registry image no tier can pull, so that job would fail at container creation.
4. `VERSION` placeholder in the archive name (above), and the two downstream `build` jobs are manual placeholders.

Scenario: `uv run j2gha run 103 --tier jenkins,act --mode full` (default branch `main`, no parameters).

`uv run j2gha analyze 103 && uv run j2gha convert 103 && uv run j2gha validate 103`: 8 jobs, automation 68.9%,
validation OK (actionlint 16 shellcheck SC2086 infos, 13 of them on the original's unquoted `${DIST_DIR}` and three on
the stand-ins' unquoted `${ROBOT}`/`${EE}`; zizmor 0; policy 5 manual-placeholder infos). The Declarative cross-check
inside `analyze` was skipped at creation time because the controller was in use.

Result (2026-10-10, Jenkins full vs act full): Jenkins **SUCCESS**, act **failure** at *Build agent image (agent dockerfile)*, verdict **differs**; archived files 1 (Jenkins) / 0 (act), differs. The converted *Run URDF tests* job builds the dockerfile agent image, which needs a Docker daemon the act and JIT runners do not have, so every later job is skipped; the Jenkins reference succeeds through all 28 stages with the archive. Found on the way: matrix `stash name: "ROBOT_${ROBOT}_urdf"` uploads are named with the GString sanitised, not expanded per cell (converter gap C16).
