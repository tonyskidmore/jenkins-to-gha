# Example 112: local twin of example 012

Derived from [example 012](../012/README.md) (owen2016/devops-practices, `jenkins/pipeline/jenkinsfile-1` at
`c04fb6c`). The original Jenkinsfile is kept verbatim in `examples/012/` as the conversion benchmark; this copy is
edited only as far as needed for the pipeline to run to completion in the harness (Jenkins full mode and the
converted workflow), so that full-mode comparison has a successful reference. Every edit is marked `// j2gha-local:`
in the Jenkinsfile.

| Line | Original | Edit | Why | Feature kept? |
|---|---|---|---|---|
| 11 | `BRANCH = "${BRANCH}"` | `BRANCH = "${env.BRANCH_NAME}"` | `BRANCH` is a job-configuration variable the harness cannot set (`--param` only reaches declared parameters), so the `when { environment name: 'BRANCH', value: 'develop' }` gates on Init and Parallel Stage never opened. With `BRANCH_NAME` the scenario `--branch develop` opens them on both sides | yes: `when`, `input` and `parallel` now execute |
| 79 | `sh 'mvn -version'` | `sh 'python3 --version'` | no Maven on the act or JIT-runner images (the Jenkins image has it) | a real `sh` step still runs |
| 80 | `sh 'mvn clean install -Dmaven.test.skip=true'` | `sh 'mkdir -p target && python3 -c "print(42)" > target/app.txt'` | the cited repository has no `pom.xml` anywhere, so the build can never succeed against it | a real `sh` step that writes a build output |
| 87 | (none) | `sh 'printf "#!/bin/sh\necho deploy\n" > deploy.sh'` inserted before `chmod 777 deploy.sh` | the cited repository has no `deploy.sh` | the original `chmod` and `./deploy.sh` steps run unchanged |

Unchanged: the agent, pipeline and stage `environment`, the `PERSON` parameter, the `input` with submitter and
parameters, `failFast`, the stage `options { timeout }`, and every `echo`.

Scenario to run: `uv run j2gha run 112 --tier jenkins,act --mode full --branch develop` (with the default branch
the gated stages are skipped on both sides, which is also equivalent but tests less).

Result (2026-10-09, Jenkins full vs act full, branch `develop`): **equivalent**, both SUCCESS; Jenkins ran
Init (input approved), Branch A, Branch B, Build, Deploy; act ran the jobs `init`, `parallel-stage-branch-a`,
`parallel-stage-branch-b`, `build`. No tests or archives on either side (the original archives nothing), so the
outputs comparison is trivial: a follow-up could add `archiveArtifacts 'target/app.txt'` to give it something to
compare, at the cost of a step the original does not have.
