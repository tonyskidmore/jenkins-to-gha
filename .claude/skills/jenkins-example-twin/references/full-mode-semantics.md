# What the harness does to a pipeline in full mode

Know this before deciding what to edit: most of a real-world Jenkinsfile already runs here unchanged, and an edit
that duplicates what the localiser does is noise in the twin. Source of truth: `j2gha/jenkins/localize.py`
(`FULL_MODE_STUBS`, `FULL_MODE_WRAPPER_STUBS`, `READ_STUBS`, `SILENT_STUBS`) and the run's own
`runs/jenkins-full/Jenkinsfile.localized`, which shows exactly what was changed and stubbed.

## Runs for real

- `sh` (under `/bin/sh -xe`, which is **dash** on the Jenkins image: no `[[ ]]`, no `time`, no bash arrays;
  the converted side runs bash), `bat`/`powershell` (will fail on Linux), `checkout scm` (the upstream repository
  at the cited commit from `source.json`), explicit `checkout`/`git` of other URLs (must be reachable),
  `dir`, `writeFile`, `readFile`, `fileExists`, `findFiles`, `stash`/`unstash`, `archiveArtifacts`, `junit`,
  `publishHTML`, `zip`/`unzip`, `withEnv`, `timeout`, `retry`, `parallel` (including dynamic
  `parallel(map.collectEntries {...})`), `input` (auto-approved), `load('file.groovy')` (the real file from the
  checkout runs: in 108 the loaded pipeline context defined the version lists the pipeline iterates over).
- `tools { maven/jdk/nodejs }` are provisioned: Maven 3.9, JDK 21 whatever the jdk name says, Node 20.
- `environment { X = sh(...) }`, `credentials()` (fake values), `parameters {}` (defaults; `--param NAME=VALUE`
  for declared parameters only).

## Stubbed (no effect, body runs where there is one)

- Steps: `build job:` (returns a SUCCESS result), `mail`, `emailext`, `slackSend`, `office365ConnectorSend`,
  `githubNotify`, `setGitHubPullRequestStatus`, `publishChecks`, `s3Upload`, `s3Download`, `copyArtifacts`,
  `waitForQualityGate`, `recordIssues`, `publishCoverage`, `recordCoverage`, `jacoco`, `cobertura`.
- Wrappers whose body runs on the built-in node: `withSonarQubeEnv`, `withAWS`, `withKubeConfig`, `withVault`,
  `azureCLI`, `container`, `sshagent`, `withDockerRegistry`, `configFileProvider` (the variable is empty),
  `withMaven`, `withGradle`, `withPythonEnv`, `podTemplate`, `wrap` (BuildUser, Xvnc...), `withDockerContainer`.
- The `docker` global (`docker.image(x).inside {}`, `docker.withRegistry {}`, `docker.build()`) without
  `--docker`: a stub whose blocks still run. With `--docker` (the host socket mounted; only for twins you wrote)
  it is real.
- Agents: `label`, `docker`, `dockerfile`, `kubernetes` → the built-in node (so a stage with its own agent gets
  a `@2` workspace with a fresh checkout, not the pipeline agent's files, unless `reuseNode`... which is also
  localised away). Build properties: `properties([...])`, `buildDiscarder`, `milestone`, `lock`.
- Unknown steps (plugins not installed, shared-library global steps): a script-level stub that returns a
  permissive object and runs a closure argument if there is one. `@Library` lines are removed; library classes
  and globals become stub objects whose every property and method returns another stub: truthy, prints as
  `j2gha-stub`, `.isEmpty()` false, iterates as empty. Job-configuration variables read as bare globals (an
  undefined `BRANCH`, `DRYRUN`...) are promoted to the same stub by the auto-repair loop.
- Credentials: every binding the analysis detects gets a fake credential (`j2gha-user` / `j2gha-fake-password` /
  `j2gha-fake-secret`), including `[$class: 'AmazonWebServicesCredentialsBinding', ...]` and a
  `credentialsId: "${name}"` whose value is a literal in the pipeline `environment {}`.

## Consequences that decide edits

- `if (output.status)` on a library result is **true** (stub is truthy) and `.isEmpty()` is false: a check that
  fails the build on a stub needs a literal stand-in result just before it, not a deleted check.
- A loop over a stub list runs zero times; a loop over a list the pipeline defines itself runs.
- `sh(returnStdout: true)` works on Jenkins, but the value is a manual item on the converted side: a command
  that depends on it will fail there (expected *differs*, not an edit).
- `archiveArtifacts` with no matching file fails the build unless `allowEmptyArchive: true`; a default `stash`
  with no matching file fails too (`allowEmpty: true` does not).
- Paths that embed `BUILD_TAG`/`BUILD_NUMBER` differ between the sides by construction.
- 16 executors on the built-in node: wide matrices run concurrently; 22 fresh clones of a large repository at
  once can hit the git plugin's 10-minute timeout (re-run, or make cells reuse the checkout).

## What is on the images (both sides, unless noted)

git, curl, unzip, zip, jq, make, python3 (`python` too), python3-yaml, Maven 3.9, JDK 21, Node 20 (act runner:
Node 24), npm, xvfb, GTK3, a `docker` client without a daemon (every `docker`/`podman`/`docker-compose` command
fails), no `wget` on the Jenkins and JIT runner images, no gcc/cmake/erlang/go/ruby/dotnet, no aws/oci/gcloud/
kubectl/helm/kind/terraform/gradle, no Kubernetes, no sudo. GitHub-hosted runners carry GitHub's own toolchain
(Maven 3.10 and newer there broke Tycho 4), so hosted runs are not toolchain-comparable.

## Reading a failed run

- `runs/jenkins-full/result.json`: `result`, `stages[]` with status, `attempts[]` with the auto-repairs applied
  (`stub-property X` = a bare global stubbed, `untype-decl`, `stringify-args`, `fill-stage`, `remove-directive`).
- `runs/jenkins-full/console.log`: grep `ERROR`, `not found`, `exit code`, `Exception`. `script.sh.copy: N:
  foo: not found` is a missing tool; `Could not find credentials entry` is an undetected binding (a harness
  gap: fix the analysis, not the twin); a failure before any stage with `J2ghaAny` in the message is a
  stub-valued directive the localiser should remove (harness gap).
- `runs/act-full/result.json`: `failed_steps`, `comparison.verdict`, `comparison.outputs` (tests and archived
  files, with `missing`/`extra` paths); `act.jsonl` has every step's output. act's bare `<nil>` error on a
  `docker cp` is act's own fault under wide fan-outs: use the self-hosted tier for those twins.
