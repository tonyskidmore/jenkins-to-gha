# Example 107: local twin of example 007

Derived from [example 007](../007/README.md) (oracle/weblogic-kubernetes-operator, `Jenkinsfile` at `a102837`). The
original is kept verbatim in `examples/007/`; this copy is edited only as far as needed for the pipeline to run to
completion in the harness. Every edited or inserted line carries `// j2gha-local:` (Groovy) or `# j2gha-local:`
(shell). Line numbers are the original file's.

The original needs an OCI compute instance: Maven settings from a config file, `oci` downloads of helm/kubectl/kind
with an instance principal, `podman` for a registry container and a two-node kind cluster, `sudo`, and the operator's
Kubernetes integration tests (hours). The twin keeps every stage and every `sh` step and replaces only the commands
that cannot run here. Where the pipeline installs a tool into its own `${WORKSPACE}/bin` (its `runtime_path`
mechanism), the twin installs a one-line stub script under the same name instead, so every later `helm`, `kubectl`,
`kind` and `podman` line runs unchanged (each stub drains a piped stdin, so the `cat <<EOF | kind create cluster`
and `| kubectl apply -f -` heredocs are safe under bash's `pipefail` on the converted side).

| Line | Original | Edit | Why | Feature kept? |
|---|---|---|---|---|
| 240 | `podman version` | `echo podman version` | no container runtime; runs before the stub is installed | the `Echo environment` step still runs `java -version`, `mvn --version`, `python --version`, `ulimit` for real (`tools { maven; jdk }` are exercised) |
| 275 | `sh "mvn -DtrimStackTrace=false clean install"` | `mkdir -p operator/target && echo built > operator/target/weblogic-kubernetes-operator.jar` | the full operator build is long and needs the `wkt-maven-settings-xml` config file (`withMaven` is a wrapper stub in full mode) | yes: the stage, the `withMaven` wrapper and a real `sh` writing a build output |
| after 282 | (none) | inserted `sh` writing `${WORKSPACE}/bin/podman` (a stub that echoes its arguments) | no container runtime; the pipeline's own `bin` directory and `runtime_path` env carry the stub to every later stage, so the registry, kind-cluster and post `podman` lines are untouched | `Make Workspace bin directory` keeps its original `mkdir` |
| 293-295 | `oci os object get ... helm-v${HELM_VERSION}.tar.gz` | one line that packs a stub `linux-amd64/helm` into `helm.tar.gz` | no `oci` CLI, no instance principal | the original `tar zxf`, `mv linux-amd64/helm ${WORKSPACE}/bin/helm`, `rm -rf`, `helm version` lines run unchanged |
| 309 | `mvn -pl kubernetes -P helm-installation-test verify` | `echo mvn ...` | the chart tests need a Kubernetes cluster | the stage and its `withMaven` wrapper |
| 323-325 | `oci os object get ... kubectl-v${KUBE_VERSION}` | one `printf` writing a stub `${WORKSPACE}/bin/kubectl` | no `oci` CLI | the original `chmod +x` and `kubectl version --client=true` |
| 339-341 | `oci os object get ... kind-v${KIND_VERSION}` | one `printf` writing a stub `${WORKSPACE}/bin/kind` | no `oci` CLI | the original `chmod +x` and `kind version`; every `kind` line in `Create kind cluster` and both `post` blocks runs unchanged against the stub |
| 390-392 | `cat .../delegate.conf`, `cat .../iptables.conf`, `lsmod\|grep ...` | each suffixed `\|\| true` | informational lines whose files/modules do not exist in a container; `sh` runs with `-e` | the commands still run |
| 399 | `sudo sysctl -w vm.max_map_count=262144` | `echo sudo sysctl ...` | no sudo | - |
| 627 | `if ! time mvn -pl integration-tests -P ${MAVEN_PROFILE_NAME} verify 2>&1 \| tee "${result_root}/kindtest.log"; then` | four inserted lines write `integration-tests/target/failsafe-reports/TEST-ItLocalTwin.xml` (2 passed cases), `${result_root}/diagnostics/ItLocalTwin/operator.log` and `${result_root}/workdir/liftandshiftworkdir/README.txt`; the `mvn` becomes `echo mvn ...` inside the unchanged `if ! ... \| tee ...; then` | the integration tests need the kind cluster, OCIR images and hours; `time` is not a dash builtin | yes: `withCredentials(usernamePassword)` with the fake credential, the `.mvn/maven.config` script, `tee` to `kindtest.log`, and real files for the stage `post` (`archiveArtifacts` matches all three patterns; `junit` reads 2 cases) |
| 655 | `sudo mv -f ${result_root}/* .../logdir/${BUILD_TAG}/wl_k8s_test_results` | `mv -f ...` | no sudo; the files are the build user's own | the move into `logdir/${BUILD_TAG}` that the archive patterns depend on |
| 678 | `sudo chown $(whoami) ${WORKSPACE}` | `chown $(whoami) ${WORKSPACE}` | no sudo; the workspace is the build user's own | the parent `post always` cleanup script runs to its end |

Unchanged: `options { timeout }`, `tools { maven 'maven-3.8.7'; jdk 'jdk25' }`, the pipeline `environment` (including
`start_time = sh(...)`), all 25 parameters, `when { anyOf { changeRequest(); branch ... } }` on the parent stage, the
`evaluate` workaround, every `script {}` block (the `_kind_image` lookup, the profile validation with
`sh(returnStatus:)`), the stage `environment { runtime_path }` blocks, the `Create kind cluster` heredocs, the
`withCredentials` binding, both `post always` blocks with `archiveArtifacts` + `junit`, and the `Sync` stage with
`when { triggeredBy; tag }` and `build job:` (a full-mode stub on Jenkins).

What this twin tests that the original cannot: a 14-stage nested declarative pipeline running end to end with
`tools`, parameters-as-environment, per-stage `environment` built from `${WORKSPACE}` and `${PATH}`, a `bin`
directory written by one stage and used by the next, `withCredentials` inside `withMaven`, and a stage `post` that
archives files under `logdir/${BUILD_TAG}/...` and publishes a JUnit report; then `Sync` gated on `triggeredBy`.
`BRANCH_NAME` must be `main` (or `release/*`) for the parent `when` to open, so the scenario is `--branch main`.

Expected differences on the converted side:

- `archiveArtifacts` paths: Jenkins archives `logdir/jenkins-ex-107-full-<n>/wl_k8s_test_results/...`, the converted
  run `logdir/gha-<owner>-<repo>-<run_number>/...` (the converter's `BUILD_TAG`). The archived *sets* will show the
  two `logdir` files as missing/extra by name; `TEST-ItLocalTwin.xml` and the two JUnit cases should match. A
  comparison that normalised `BUILD_TAG`/`BUILD_NUMBER` path segments would make this an equivalent twin; the two
  diagnostics lines can be removed to the same effect.
- `jdk 'jdk25'` is JDK 21 on Jenkins and `setup-java` 25 on GHA (H4); `java -version` output only.
- `[ "${MAVEN_PROFILE_NAME}" == "kind-sequential" ]` (lines 569/571, unchanged) prints `unexpected operator` under
  dash on Jenkins (status 2 inside `if`, no effect) and is accepted by bash on GHA; `PARALLEL_RUN` is unchanged on
  both sides.
- `evaluate`, `_kind_image`, `currentBuild.description`, `res` are manual/placeholder items on GHA; none of them
  changes the shell that runs (`kind_image` is empty in the heredoc the stub `kind` ignores).
- `build job: wkt-sync` is a stub on Jenkins and a `::warning` placeholder on GHA.
- Hosted/act runners get Maven from their image (C15: no setup step for the `maven` tool).

Scenario: `uv run j2gha run 107 --tier jenkins,act --mode full --branch main` (the default `KIND_VERSION`/
`KUBE_VERSION` pair `0.32.0`/`1.36.1` resolves in `kind_k8s_map`; `MAVEN_PROFILE_NAME=wls-srg` with an empty
`IT_TEST` passes the profile validation). The converted workflow is a single job, so no workspace hand-off is involved.

Note: `analyze` was run while the controller was busy, so Jenkins' own Declarative validation (`toJson`) of the twin
has not been cross-checked yet; the Groovy AST parse succeeded.

Result (2026-10-10, Jenkins full vs act full): Jenkins **SUCCESS**, act **success**, verdict **differs**; JUnit cases 2 (Jenkins) / 2 (act), same; archived files 3 (Jenkins) / 3 (act), differs. Both sides succeed with the same 2 JUnit cases and 3 archived files; the verdict is *differs* only because two archive paths embed `BUILD_TAG` (`jenkins-ex-107-full-N` against `gha-...`), a run identifier the comparison does not normalise (follow-up H13).

Self-hosted tier (2026-10-10): **differs** (same as act).
