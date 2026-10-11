# Example 000 video series: Jenkins to GitHub Actions

For the viewer's guide to the series, start with [docs/walkthrough-videos.md](../walkthrough-videos.md). This page is for people rebuilding the videos.

Five narrated chapters made with the `narrated-explainer` skill (`.claude/skills/narrated-explainer/`). This folder holds the *inputs*. The generated audio and video are not stored here, and neither are the two live screen
captures (see below).

| Chapter | README parts | Project (inputs) |
|---|---|---|
| 1 Baseline on Jenkins | 1 | `000-ch1-baseline-on-jenkins/` |
| 2 Analyse, convert, validate | 2-4 | `000-ch2-analyse-convert-validate/` |
| 3 Differential runs | 5-6 | `000-ch3-differential-runs/` |
| 4 Real GitHub Actions | 7 | `000-ch4-real-github-actions/` |
| 5 Break the conversion | 8 | `000-ch5-break-the-conversion/` |

Each project holds `scenes.json` (the script), `pronunciations.json`, `captures/` (REAL command output plus the `.sh` that produced it),
`shots/` (real browser screenshots, chapters 1, 3 and 4) and `source-facts.md`. Generated output lives in `.cache/video/<project>/`
(gitignored): `audio/`, `clips/`, `timeline.json`, `out/video.mp4`.

Rebuild a chapter (from the repo root; `nx` = `.claude/skills/narrated-explainer/scripts/nx`):

    nx check    --script docs/video/<p>/scenes.json --work .cache/video/<p>
    nx audio    --script docs/video/<p>/scenes.json --work .cache/video/<p>
    nx clips    --script docs/video/<p>/scenes.json --work .cache/video/<p>   # chapters 1 and 4 only (live footage)
    nx timeline --script docs/video/<p>/scenes.json --work .cache/video/<p>
    nx render   --work .cache/video/<p>          # then: nx qa --work .cache/video/<p>
    nx concat   OUT.mp4 ch1.mp4 ch2.mp4 ch3.mp4 ch4.mp4 ch5.mp4

Chapter 4's GitHub screenshots are committed in `000-ch4-real-github-actions/shots/` (with `shots/shots.example.json`, a template: the real spec names the account and runs, so it stays in `.cache/video/000-ch4-real-github-actions/shots.json`), so a re-render needs no
GitHub access, provided chapter 4's live capture already exists locally (see below). Re-shooting them needs a profile signed in with `nx shots --login`; the capture is read-only.
Re-capturing needs the local Jenkins, Docker and (chapter 4 only) GitHub access and Actions minutes: see each `captures/*.sh`.
Chapter 4's redaction rules (`redact.txt`) are deliberately kept in `.cache/video/000-ch4-real-github-actions/`, not here: they name the
account and repository they hide.

**The live footage is not committed.** Chapters 1 (scene `07b-live`) and 4 (scene `05d-live`) play screen recordings made
by the `hyperframes-walkthrough` skill for the 60-second video; their `scenes.json` reads them from
`.cache/video/000-walkthrough-60s/capture/jenkins` and `.../capture/gha` (gitignored: large, and the GitHub recording
shows the account before masking). From a fresh clone, record new captures (`hfw capture jenkins|gha --work
.cache/video/000-walkthrough-60s ...`, options in the `hyperframes-walkthrough` skill; the GitHub one starts a
self-hosted workflow run), then re-time each clip's
`trimStart`, `trimEnd` and `segments` in the chapter's `scenes.json` to the new recording, because the cut points belong
to the old one. Every other chapter rebuilds from what is committed.
