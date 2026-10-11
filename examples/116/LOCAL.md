# Example 116: local twin of example 016

Derived from [example 016](../016/README.md) (dvsa/cvs-auto-mobile-app-retired, `Jenkinsfile` at `bf150f6`). The
original is kept verbatim in `examples/016/` as the conversion benchmark; this copy is edited only as far as needed
for the pipeline to run to completion in the harness (Jenkins full mode and the converted workflow). Every edit is
marked `// j2gha-local:` in the Jenkinsfile.

| Line | Original | Edit | Why | Feature kept? |
|---|---|---|---|---|
| 19 | `withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', accessKeyVariable: 'AWS_ACCESS_KEY_ID', credentialsId: 'jenkins-iam', secretKeyVariable: 'AWS_SECRET_ACCESS_KEY']])` | `withCredentials([usernamePassword(credentialsId: 'jenkins-iam', usernameVariable: 'AWS_ACCESS_KEY_ID', passwordVariable: 'AWS_SECRET_ACCESS_KEY')])` | `analyze` only detects symbol-form bindings (`usernamePassword(...)`, not `[$class: ...]` maps), so the harness never creates a fake `jenkins-iam` credential, and with the `aws-credentials` plugin now installed the real binding fails on Jenkins with *could not find credentials*; the provisioning script can fake only username/password, string, file and SSH-key types (H6). Same credential id, same two variable names | mostly: the `withCredentials` wrapper, its id and its variables; the AWS-specific binding type is lost. If `analyze` learns `$class` bindings and the provisioning script an `AWSCredentialsImpl` fake, this line can revert |
| 20 | `sh "aws s3 cp s3://dvsa-cvs-mobile-artefacts/files/${LBRANCH}.txt ${LBRANCH}.txt"` | `sh "test -n \"\$AWS_ACCESS_KEY_ID\" && echo https://raw.githubusercontent.com/dvsa/cvs-auto-mobile-app-retired/bf150f6.../README.md > ${LBRANCH}.txt"` | no `aws` CLI on either image and no bucket. The pointer file still holds a download URL (GitHub, the one network the twins may use) and the bound access key is still read | a real `sh` inside the credentials binding, writing the same file the next stage reads |
| 25 | `sh "wget -O CVSMobile.ipa `cat ${LBRANCH}.txt`"` | `sh "curl -sSfLo CVSMobile.ipa `cat ${LBRANCH}.txt`"` | neither the Jenkins image nor the JIT-runner image has `wget` (the act image does); `curl` fetches the URL the pointer file names, so the `cat`-the-pointer-file chain stays | yes: the download of the artefact named by the pointer file, into the file the upload step reads |
| 27 | `APP_ID=sh(script: 'curl -u $BROWSERSTACK_CREDS -X POST "https://api-cloud.browserstack.com/app-automate/upload" -F "file=@CVSMobile.ipa" \| jq ".app_url"', returnStdout: true).trim()` | `APP_ID=sh(script: 'test -n "$BROWSERSTACK_CREDS" && echo \'{"app_url":"bs://j2gha-local"}\' \| jq ".app_url"', returnStdout: true).trim()` | no BrowserStack account; the same JSON shape goes through the same `jq` filter, the `usernameColonPassword` binding is still read, and `APP_ID` still comes from `sh(returnStdout: true).trim()` (`"bs://j2gha-local"`, quoted as the original's `jq` output was) | yes: the credentials binding, `returnStdout`, `jq`, the Groovy variable |
| 33 | `sh "mvn --batch-mode clean install -PCI-Browserstack -DBROWSERSTACK_APP_ID=${APP_ID} -Dorg.slf4j...=warn"` | `-PCI-Browserstack` removed, `-DskipTests` added | the profile runs the Serenity/Appium suite against a BrowserStack device, and its `serenity-maven-plugin:2.0.20:aggregate` goal fails on JDK 21 before any test (Guice's cglib cannot open `java.lang`; verified in `j2gha/runner:local`). Without the profile `mvn -B -DskipTests clean install` builds the project from Maven Central in 3 min 25 s cold (compile 291 sources, jar, test-jar, `dependency-jars/`, `mobile-automation.zip`) | yes: a real Maven build of the cited commit inside the (stubbed) `browserstack` wrapper, still passing `-DBROWSERSTACK_APP_ID=${APP_ID}` |
| 38 (inserted) | none | `sh 'mkdir -p target/site/serenity && echo "<html>...</html>" > target/site/serenity/index.html'` before `publishHTML` | the report directory was produced by the profile's `serenity:aggregate` dropped above; writing it by hand keeps `publishHTML` with `allowMissing: false` and the same `reportDir`/`reportFiles` | yes: `publishHTML` unchanged |

Unchanged: `podTemplate`/`containerTemplate`/`container('maven')` (stubbed wrappers on Jenkins, manual placeholders
on the converted side), `node(label)` (rewritten to `built-in` by the localiser), `withFolderProperties { LBRANCH =
... }` (an unknown step whose body runs; `env.BRANCH` is unset on the harness, so `LBRANCH` is `null` and the
pointer file is `null.txt`), the `APP_ID` variable, the five stages and `publishHTML` with every option.

What this twin tests: a scripted `podTemplate { node { container { ... } } }` pipeline with two credentials
bindings, a Groovy variable fed by `sh(returnStdout: true)`, a real Maven build (JDK 21, Maven 3.9, about 3.5 min
cold on every tier, so within the full-mode 10-minute cap, H9) and `publishHTML`. There is no `junit` or
`archiveArtifacts`, so the outputs comparison is trivial (`publishHTML` is not compared); the value is the credential
bindings and the real build succeeding on both sides, and the converted side's handling of the manual items below.

Known or expected differences on the converted side:

- `withFolderProperties` is a manual placeholder, so `LBRANCH` is empty on GitHub Actions: the pointer file is `.txt`
  there and `null.txt` on Jenkins. Each side writes and reads its own name, so both succeed.
- `APP_ID` is a Groovy variable the converter does not carry over, so the Maven step gets
  `-DBROWSERSTACK_APP_ID=` (empty); harmless with `-DskipTests`.
- `podTemplate`, `container` and `browserstack` are manual placeholders (`echo "::warning::..."`); the Maven build
  runs directly on the runner, which the harness images equip with the same toolchain.
- The AWS binding now maps to `secrets.JENKINS_IAM_USR` / `secrets.JENKINS_IAM_PSW` (the original `$class` binding
  produced no `env` at all, H6); the harness replaces both with fake values.
- The `publishHTML` upload gets `if: always()` (C14), which does not matter on a green run.
- `analyze` now sees two credentials (difficulty 45 against the original's 44).

Scenario: `uv run j2gha run 116 --tier jenkins,act --mode full` (the repository's default branch is `develop`;
nothing in the pipeline reads the branch name, `env.BRANCH` is a folder property, so no `--branch` or `--param` is
needed).

Expected: Jenkins SUCCESS through checkout, Get IPA from AWS S3, install ipa in browserstack, test (Maven build) and
create report; act: the one job `main` succeeds (three placeholder warnings, the same five real steps, an
`html-report-9` artifact); verdict **equivalent**, no tests or archives on either side.

Result: (to be recorded after the run)

Result (2026-10-10, Jenkins full vs act full): Jenkins **SUCCESS**, act **success**, verdict **equivalent**. A real `mvn -DskipTests install` of the mobile test project on both sides (about 3.5 minutes cold); publishHTML is not compared, so the outputs are trivial.

Self-hosted tier (2026-10-10): **equivalent** (same as act).
