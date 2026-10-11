# Example 111: local twin of example 011

Derived from [example 011](../011/README.md) (oneanupam/jenkins-shared-libs, `vars/pipeline.groovy` at `c4b839d`).
The original is kept verbatim in `examples/011/` as the conversion benchmark; this copy is edited only as far as
needed for the pipeline to run to completion in the harness (Jenkins full mode and the converted workflow). Every
edit is marked `// j2gha-local:` in the Jenkinsfile.

| Line | Original | Edit | Why | Feature kept? |
|---|---|---|---|---|
| 4-8 | `Map settings = PipelineDefaults.resolve(config, libraryResource('in/oneanupam/jenkins/pipeline.properties'), env.JOB_NAME)` | `Map settings = [application: 'application'] + config` (one line) | the harness stubs the library class `PipelineDefaults` and `libraryResource` instead of loading them from the checkout (H8), so every setting resolved to the string `j2gha-stub` and the Install stage ran the command `j2gha-stub` (exit 127). `application` keeps the value of `resources/in/oneanupam/jenkins/pipeline.properties` (the real `resolve()` would replace it with `JOB_NAME`); `+ config` keeps the template's "caller's config overrides the defaults" contract. The other five keys are inlined at their use sites (next rows) because the converter emits a non-literal `sh`/`junit`/`archiveArtifacts` argument as literal text (C7: `run: settings.installCommand`), so a map could never reach the converted side | partly: `def call(Map config)` and the harness's `call(new J2ghaConfig())` invocation stay, `String application = settings.application` and `APPLICATION_NAME` stay; the `libraryResource` and `src/` class resolution are gone (the harness cannot run them either way) |
| 33 | `sh settings.installCommand` (`npm ci` in the properties) | `sh 'echo install'` | the cited repository is the shared library itself: no `package.json`, nothing to install; and C7 | a real `sh` step in the Install stage |
| 39 | `sh settings.testCommand` (`npm test -- --ci`) | `sh 'mkdir -p reports && printf '<testsuite ...><testcase classname="unit" name="smoke"/></testsuite>' > reports/junit-unit.xml'` | no tests upstream; writes one passing JUnit case in a file that matches the `testResultsPattern` (`**/junit-*.xml`), so the `junit` step and the outputs comparison have one real test case | a real `sh` step whose output the `post` reports |
| 45 | `sh settings.buildCommand` (`npm run build`) | `sh 'mkdir -p dist && cp README.md dist/'` | no build upstream; writes one file that matches the `artifactPattern` (`dist/**`) | a real `sh` step whose output the `post` archives |
| 52 | `junit testResults: settings.testResultsPattern, allowEmptyResults: true` | `junit testResults: '**/junit-*.xml', allowEmptyResults: true` | the same value as the properties file, inlined (C7: the converter emitted `J2GHA_JUNIT: settings.testResultsPattern`) | yes: `junit` with `allowEmptyResults` in `post { always }` |
| 53 | `archiveArtifacts artifacts: settings.artifactPattern, allowEmptyArchive: true` | `archiveArtifacts artifacts: 'dist/**', allowEmptyArchive: true` | the same value as the properties file, inlined (C7: the converter emitted `path: settings.artifactPattern`) | yes: `archiveArtifacts` with `allowEmptyArchive` in `post { always }` |

Unchanged: the `import` (the localiser removes it on both twins), `def call(Map config = [:])`, `agent any`, the three
`options` (`timestamps`, `disableConcurrentBuilds`, `skipDefaultCheckout`), `environment { APPLICATION_NAME }`,
the explicit `checkout scm` stage, the four stage names, and `post { always / success / failure }`.

What this twin tests: a Declarative library template (the harness appends `call(new J2ghaConfig())`) whose four
stages run real `sh` commands and whose `post { always }` records a JUnit report and archives a file on both sides,
so the full-mode outputs comparison has one test case (`unit.smoke`, passed) and one archived file (`dist/README.md`)
to compare rather than two empty sets. It does **not** test the library-template aspect proper (defaults from
`libraryResource`, `PipelineDefaults.resolve`): the harness cannot load the library from the checkout (H8), and the
converter cannot follow a map lookup into a `sh` argument (C7), so a twin that kept the map would run placeholder
text on both sides, as the original did. If H8 and C7 are done, the map can get its five keys back and
the five inlined sites can revert to `settings.*`.

Known or expected differences on the converted side:

- `APPLICATION_NAME` is `TODO-j2gha: application` on GitHub Actions (`String application = settings.application` is a
  script variable the converter does not carry over), so the `post` echoes read `TODO-j2gha: application completed
  successfully` instead of `application completed successfully`. Echo text is not compared.
- The converted job checks the source out twice (the harness's own checkout of the cited commit, then the
  `Checkout: checkout` step); `skipDefaultCheckout(true)` has no converted equivalent. Harmless.
- `disableConcurrentBuilds()` becomes a `concurrency` group; `timestamps()` has no equivalent (GitHub timestamps
  every log line).

Scenario: `uv run j2gha run 111 --tier jenkins,act --mode full` (default branch `main`; no parameters).

Expected: Jenkins SUCCESS through Checkout, Install, Test, Build and `Declarative: Post Actions` (junit: 1 test,
archive: `dist/README.md`, echo `application completed successfully`); act: the one job `checkout` (Checkout,
Install, Test, Build) succeeds, the junit summary reports 1 test and the two uploads carry `reports/junit-unit.xml`
and `dist/README.md`; verdict **equivalent** with 1 matching JUnit case and 1 matching archived path on each side.

Result: (to be recorded after the run)

Result (2026-10-10, Jenkins full vs act full): Jenkins **SUCCESS**, act **success**, verdict **equivalent**; JUnit cases 1 (Jenkins) / 1 (act), same; archived files 1 (Jenkins) / 1 (act), same. One JUnit case and one archived file compared on both sides.

Self-hosted tier (2026-10-10): **equivalent** (same as act).
