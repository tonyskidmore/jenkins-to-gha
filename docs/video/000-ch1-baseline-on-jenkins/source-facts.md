# Source facts: chapter "Run it on Jenkins first" (examples/000/README.md Part 1)

Environment: disposable Jenkins 2.580.1 (j2gha controller, reset with `j2gha jenkins down` then `up` for this recording).
Screenshots: shots/*.png (made with `nx shots`, spec shots/shots.json). Terminal: captures/verify-and-logs.txt.

## How the recording was made (stated on screen)
The user approved doing this through Jenkins' HTTP API instead of the UI: two credentials, the job (CpsFlowDefinition
from examples/000/Jenkinsfile, sandbox on), build #1 with defaults, input approved with CHANGE_TICKET=CHG-1234,
build #2 with RELEASE_VERSION=1.5.0-SNAPSHOT, DEPLOY_ENV=none, RUN_INTEGRATION_TESTS=false.
The UI screens are real; the form-filling was not done by clicking.

Exception, scene 07b-live: live footage from a separate recording (hyperframes-walkthrough capture
`.cache/video/000-walkthrough-60s/capture/jenkins`, gitignored; built with `nx clips`). There the job was build #1,
it paused at the Deploy gate, CHANGE_TICKET was typed as CHG-1234 and Deploy was clicked on camera; result SUCCESS.
[capture timeline.json `build`, `result`, events `input-pending`, `ticket-typed`, `deploy-click`, `build-finished`;
docs/video/000-walkthrough-60s/source-facts.md Act 1] Speeds come from the edit and are labelled on screen.

## Safe claims
- Pipeline stages and constructs: README "The pipeline". Graph in Pipeline Overview confirms 3 parallel branches, 3 matrix cells. [shots/04, 07]
- Credentials list shows artifact-repo (ci-uploader/******) and inventory-deploy-token. [shots/02]
- Build #1 default params, paused at Deploy with "Deploy this inventory-service release?" and CHANGE_TICKET default CHG-0000. [shots/04, 05]
- Console: "Approved by admin"; "Uploaded to repository/inventory-service/1.4.0 as ci-uploader (password: 15 characters)";
  "Deploying 1.4.0 to staging (deploy token is set)"; "inventory-service-1.4.0-b1 finished: SUCCESS". [capture #6, shots/12]
- Build #1: green, display name "#1 1.4.0 to staging", 5 artifacts (lint.txt, staging.json, BUILD_INFO.txt, tar.gz, .sha256), "approved by user admin". [shots/06]
- Tests: 21, 0 failures, 5 packages (1 + 5 + 5 + 5 + 5). [shots/08]
- Fingerprints: the three dist/ files. [shots/11]
- 1.6 commands: sha256sum OK; BUILD_INFO python=3.13.5; staging.json has CHG-1234 and admin; CLI prints
  {"backend": "memory", "stock": {"gadget": 1, "widget": 2}, "version": "1.4.0"}. [capture #0-5]
- Build #2: no approval; Integration tests, Publish, Deploy not executed (skipped markers); 20 tests; only lint.txt archived;
  log has "Snapshot build: the Publish stage will be skipped" and three "skipped due to when conditional" lines. [shots/16, 17, 15; capture #7]
- Job page shows test trend 21 to 20 and both builds. [shots/13]

## Differences from README Part 1 (real behaviour)
- 1.1: not re-captured (reset was run by the agent; the README's "Jenkins ready at ..." line is not shown).
- 1.3/1.4: README says click Build Now; with the job created via API the first build was started via POST /build; the sidebar shows "Build with Parameters" afterwards.
- 1.5: README says "build finishes within seconds"; Deploy stage shows 1 min only because the build waited for approval.
- 1.6 Tests: README names suites "tests.unit (5), tests.integration.sqlite (1), tests.unit.memory.json ..."; this Jenkins' Tests page shows
  packages "tests.unit.test_core", "tests.integration.sqlite.test_cli", "tests.unit.memory.json.test_core" etc. Counts agree (21, 5 groups).
- 1.4/1.6 Pipeline Overview: it is at /job/inventory-service/1/stages; matrix cell names are truncated ("Matrix - INVE...") and each cell has an inner stage called "Contract tests"; README calls cells sqlite/text etc. A "Post Actions" stage also appears.
- 1.6 Log: README quotes exactly the console lines; all four matched.
- 1.7: README says "the job page's Stages view shows both builds side by side": real page /job/inventory-service/multi-pipeline-graph (sidebar "Stages"); shown in shots/14 but not used in the script.

## Do not claim
- That the approval of the chapter's own builds was clicked in the browser (it was sent by API); only the separate
  recording in 07b-live was clicked.
- That 07b-live is the same build #1 as the screenshots (it is another recording).
- That the Jenkins UI times are system times (console shows UTC, stage view shows browser time zone).
- That this proves anything about GitHub Actions: nothing converted or run there.
- That the memory/text matrix exclusion was visibly shown (only three cells are shown; names truncated).
- Anything about the audio (not generated).
