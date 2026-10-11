# Example 115: local twin of example 015

Derived from [example 015](../015/README.md) (IBM/cloudant-node-sdk, `Jenkinsfile` at `e775c33`). The original is
kept verbatim in `examples/015/`; this copy is edited only as far as needed for the pipeline to run to completion in
the harness. Every edit is marked `// j2gha-local:` in the Jenkinsfile.

| Line | Original | Edit | Why | Feature kept? |
|---|---|---|---|---|
| 51-52 | `sh './scripts/setup_couch.sh'`, `sh './scripts/setup_wiremock.sh'` | behind `echo` | the scripts wait 120 s for a CouchDB on 127.0.0.1:5984 and a WireMock on :8080 that only IBM's pod template provides (and 8080 is the Jenkins controller's own port inside its container) | the `withEnv`, `withCredentials` and stage `post { junit }` around them |
| 359, 364 | `registryArtifactoryUp()`/`registryArtifactoryDown()` return IBM Artifactory URLs built from `env.ARTIFACTORY_URL_*` | return `https://registry.npmjs.org/` | the Artifactory server objects are stubs here, so the URLs were `j2gha-stub/api/npm/...` | the `withNpmEnv` helper and its `NPM_CONFIG_REGISTRY` plumbing |
| 374 | `NPM_CONFIG_USERCONFIG=.npmrc-jenkins` | `NPM_CONFIG_USERCONFIG=/dev/null` | `.npmrc-jenkins` sets an `_authToken` for the registry scope; with the harness's fake token the public registry would answer 401 | the `withEnv` |
| 384 | `sh 'npm test'` | `sh 'npm run test-unit'` | `npm test` runs the integration tests, which need CouchDB and WireMock; `test-unit` builds (`tsc`) and runs the unit tests, and jest-junit still writes `junitreports/*.xml` for the `junit` step | a real `npm ci`, build and test run with JUnit output |
| 411 | `npm publish --tag ${tag} ./dist` | `npm pack ./dist` | no publishing rights, and nothing must be published from a test harness. A first attempt used `npm publish --dry-run`, which the registry refused ("cannot publish over the previously published versions: 0.12.11") because the version bump before it, `bumpVersion` from the library, is a stub. *Publish[staging]* runs on every non-tag build, so the twin still exercises `npm run build` and packs the tarball | `publishNpm`, `publishStaging`, their `withCredentials` |

Unchanged: the Kubernetes agent with the library pod template (localised to `agent any`; converted to a hosted
runner), the `validatingString` parameter, `credentials()` in `environment`, the library steps `detectSecrets`,
`defaultInit`, `applyCustomizations`, `bumpVersion`, `customizePublishingInfo`, `publishArtifactoryBuildInfo`,
`gitsh` (all stubbed on Jenkins, placeholders on the converted side), every `when` (the Sonar, Gauge, Mend, tag and
public-publish stages are skipped in the default scenario), the closures reassigned at run time, and the stage
`post` blocks.

Needs on both sides: Node 20 or later and network access to registry.npmjs.org. Expected duration: a few minutes
(`npm ci`, `tsc`, jest).

Scenario: `uv run j2gha run 115 --tier jenkins,act --mode full` (default branch `main`, `TARGET_VERSION=NONE`).

Result (2026-10-09, Jenkins full vs act full, two runs): the real `npm ci`, `tsc` build and 1,965 jest unit tests
run on both sides and the JUnit cases are compared one to one. Jenkins **FAILURE** at QA both times: the same test,
`ChangesResultIterator testNextWithFiniteErrorTolerance transientErrors`, fails ("promise resolved instead of
rejected") while the other 1,964 pass; act passes all 1,965. The same test file passes in both the Jenkins image and
the act runner image when run outside Jenkins (Node 20 and Node 24), so this is a timing-dependent test that fails
under Jenkins' durable `sh` on this host, not a conversion or toolchain difference. Verdict *differs* (one test case
with a different status); act's first run also failed at *Publish[staging]* on the dry-run publish, which is why the
twin now packs instead.
