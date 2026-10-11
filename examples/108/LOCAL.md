# Example 108: local twin of example 008

Derived from [example 008](../008/README.md) (h2oai/h2o-3, `docker/Jenkinsfile-build-docker` at `f26129f`). The
original is kept verbatim in `examples/008/`; this copy is edited only as far as needed for the pipeline to run to
completion on the harness's Jenkins in full mode. Every edited or inserted line is marked `// j2gha-local:` /
`# j2gha-local:` in the Jenkinsfile. Line numbers below are the original's (the twin's in brackets where inserted
lines shift them).

| Line | Original | Edit | Why | Feature kept? |
|---|---|---|---|---|
| 28 | `sh "docker save -o ${image}.tar ${H2O_ECR}/h2o-3/${image}"` | `sh "echo docker save ... > ${image}.tar"` | no Docker daemon; the echoed command becomes the "image tarball" that `stash includes: "${image}.tar"` carries | `stashDockerImage`: the `sh`, the `stash` and the `rm` |
| 35 | `sh "docker load -i ${image}.tar"` | `sh "echo docker load -i ${image}.tar"` | no Docker daemon; the unchanged `rm ${image}.tar` on the next line still fails if the `unstash` did not deliver the file | `unstashDockerImage`: the `unstash`, the `sh` and the `rm`, and the whole `unstashDockerImages` dependency switch (`dev-jdk-8-base` needs `dev-base`, `dev-build-base` needs `dev-r-4.5.2`, ...) |
| 91, 184 | `buildSummary.stageWithSummary(name) { ... }` | `stage(name) { ... }` | `buildSummary` is a global of the private `test-shared-library`; the harness stubs it and runs the block without a stage boundary, so every step of the 008 trace landed in `(no stage)`. `stage()` keeps the names (`Checkout and Init`, `Build <target>`) the trace comparison and the converter use. The one structural edit of this twin | `buildSummary(...)`, `buildSummary.get().addStagesSummary(...)` and `buildSummary.refreshStage(name)` stay as stubbed calls |
| 114-122 | `sh "s3cmd get s3://artifacts.h2o.ai/releases/oracle/jdk-N/x64-linux/<tarball>"` (x9) | `sh "echo s3cmd get ... > <tarball>"` (x9) | the bucket is private; each stand-in writes a file of the exact tarball name into `docker/`, so `stash name: 'docker-sources'` carries the Oracle JDK stand-ins with the Dockerfiles, as the real stash would | `dir('docker')`, `withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', ...]])` with the fake AWS keys (the 008 full run stopped here on a missing credential; the harness now provisions it), `docker.image('d3fk/s3cmd').inside(...)` (its body runs on the built-in node in full mode) and the `stash` |
| 195 [194-202] | `make CI=1 H2O_BRANCH=... VERSION=... PUSH=... NO_CACHE=... <target>` | `echo make ...` (a `// j2gha-local` comment line above the `sh """`, since a backslash-continued line cannot carry a trailing marker) | every Makefile target is `docker build` (and `docker push` when `PUSH=true`); no daemon. All five `${...}` interpolations are unchanged: `VERSION` comes from the real `pipelineContext.getBuildConfig().getDefaultImageVersion()` (47 at this commit), `NO_CACHE` from `params.noCache` | `unstash 'docker-sources'`, the `params.*` reads, the `imageExistsH2OECR(...) || params.forceBuild` gate and `stashDockerImages(target)` |
| 215 [216] | `sh(script: 'aws ecr get-login-password --region us-east-1', returnStdout: true)` | `'echo aws ecr get-login-password ...'` | no AWS CLI or account; the echoed command stands in for the password (`H2O_ECR_PWD`) | `dockerLoginH2OECR()` with its `withCredentials` AWS binding (fake keys) |
| 217 [218] | `docker login --username AWS --password $H2O_ECR_PWD $H2O_ECR` | behind `echo` | no Docker daemon, no ECR | as above |
| 227 [227-228] | `sh(script: "aws ecr batch-get-image ... --output text", returnStdout: true)` | `"echo aws ecr batch-get-image ..."` (marker on a comment line above: a trailing comment inside the call made the receiver text exceed 300 characters, which crashes the AST dumper, see below) | no AWS CLI; the echoed command never equals `tag`, so `imageExistsH2OECR` returns `false` and every image is built, as against an empty registry (with the CLI missing the original would have thrown and hit the same `return false`) | `imageExistsH2OECR` with its `try/catch` and `withCredentials` |

Unchanged on purpose: `@Library('test-shared-library@dai-updated') _` and `import ai.h2o.ci.buildsummary.StagesSummary`
(the localiser removes them and stubs the classes), `properties([parameters([...])])` (the harness registers
`forceBuild=false`, `publish=false`, `h2oBranch=master`, `noCache=true` from these definitions), `ansiColor`,
`timestamps`, `cleanWs`, `checkout scm`, **`load('scripts/jenkins/groovy/pipelineContext.groovy')`**, both `node
(DEFAULT_LABEL)` (localised to the built-in node), `buildInParallel` with `parallel(targets.collectEntries {...})`, and
every `PYTHON_VERSIONS`/`R_VERSIONS`/`JDK_VERSIONS` loop.

About `load`: in full mode the harness runs `load()` for real (`READ_STUBS` apply to trace mode only), and the 008
full-mode console shows the real `pipelineContext.groovy` loading `buildSummary.groovy`, `buildConfig.groovy`,
`pipelineUtils.groovy`, `emailer.groovy` and `healthChecker.groovy` from the h2o-3 checkout and running their `git
log`/`sed`/`grep` steps without error. So `PYTHON_VERSIONS` and `R_VERSIONS` are the repository's own lists
(`['3.7', '3.8', '3.9', '3.10', '3.11']` and `['3.4.1', '3.5.3', '4.0.2', '4.4.0', '4.5.2']` at this commit) and no
literal lists were added: the pipeline builds its real 52 targets (1 + 2 + 1 + 5 + 1 + 9 + 1 + 1 + 1 + 15 + 15),
and the stash dependency chain (`dev-build-base` needs `dev-r-4.5.2`, `dev-r-base` needs `dev-python-3.7`) resolves
because those versions are in the real lists. In trace mode `load` is a stub, the lists iterate as empty and only
the 12 fixed targets run; that is the original 008's trace behaviour too.

What this twin tests: a scripted pipeline whose stage graph is computed at run time (`parallel` over
`collectEntries`, 11 waves of 1 to 15 branches), stash/unstash of a build product between waves on a dependency
switch, `params.*` from `properties([parameters([...])])`, two map-form AWS credential bindings, `docker.image().inside`
and a `load()`ed helper used across every stage. The outputs comparison has no tests and no archives on either side;
the comparison is per-stage results and the stage set.

Expected on the converted side (`uv run j2gha convert 108`: 1 job, automation 43.5%): the converter emits only
*Checkout and Init* (checkout, `cleanWs`, `dir docker`, the nine `echo s3cmd` steps, `stash docker-sources`); `load`,
`pipelineContextFactory` and `getDefaultImageVersion` are manual placeholders and `parallel(targets.collectEntries
{...})` is reported as serialised but produces no steps, so none of the 52 *Build <target>* stages exist on the
converted side. Two things to know before running it:

- The converter maps `docker.image('d3fk/s3cmd').inside(...)` to a `docker run --rm -v "$PWD":"$PWD" ... d3fk/s3cmd sh -c
  '...'` wrapper around each of the nine `echo s3cmd` steps. On act and the self-hosted tier the job containers have no
  Docker socket, so the converted run fails at the first of them (*Checkout and Init*, step `s10`); on the hosted tier
  (`ubuntu-latest` has a daemon, the image is public) they pass. If the daemon-less tiers should reach the stash, the
  one further edit is to replace line 113's `docker.image('d3fk/s3cmd').inside("...") {` by a harmless wrapper such
  as `withEnv(["J2GHA_WAS_DOCKER_IMAGE=d3fk/s3cmd"]) {`, which loses the `docker.inside` feature; not done here.
- **Expected verdict: Jenkins SUCCESS (53 stages), converted run failure at *Checkout and Init* on act/self-hosted
  (or success with 52 missing stages on hosted), *differs*** either way: the reproducible statement that
  run-time-computed `parallel` maps are not converted (`DynamicParallel`, the hard finding on 008).

Scenario: `uv run j2gha run 108 --tier jenkins,act --mode full` (default branch `master`; the parameters take their
defaults, so `publish=false` keeps the stash/unstash path and `noCache=true` adds `--no-cache` to the echoed `make`).
The Jenkins run clones h2o-3 once (about 70 s), then runs 52 short `Build <target>` stages in 11 waves on the 16
executors of the built-in node, each one an `unstash` of the 118-file `docker/` tree plus two or three `sh` echoes.

Harness note found while making this twin: `docker/jenkins/groovy/ast_dump.groovy` truncates receiver/property texts
longer than 300 characters with `StringBuilder.setLength(max)`, which Groovy 2.4 on a modern JDK cannot dispatch
(`setLength` is inherited from the non-public `AbstractStringBuilder`): any Jenkinsfile with such an expression is
reported *unparseable* (`dumper failure: ... StringBuilder.setLength() ... [300]`). The twin avoids it by keeping its
marker outside the `sh(...)` receiver at line 227; `sb.delete(max, sb.length())` would fix the dumper.

Results: to be recorded by the run.

Result (2026-10-10, Jenkins full vs act full): Jenkins **SUCCESS**, act **failure** at *Checkout*, verdict **differs**. Only *Checkout and Init* exists on the converted side (the loaded `pipelineContext.groovy` and the dynamic `parallel` are manual), and its `docker.image().inside` steps become `docker run` without a daemon; the Jenkins reference succeeds through 53 stages (the real pipeline context loads, 52 build stages in parallel waves).
