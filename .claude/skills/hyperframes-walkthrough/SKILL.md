---
name: hyperframes-walkthrough
description: Make the 60-second HyperFrames walkthrough video for a j2gha example - Jenkins baseline, analyse/convert/validate, differential trace, real GitHub Actions - with LIVE screen captures of the actual Jenkins build and GitHub Actions run playing inside the video's browser frames (video-in-video), local Kokoro narration and an ambient soundtrack, rendered to 1080p MP4 with HyperFrames; and publish finished videos as GitHub release assets. Use whenever the user wants a short walkthrough, promo or demo video of an example (examples/NNN) or of the harness, wants the real pipeline/workflow runs filmed rather than screenshots, wants to re-capture, re-cut or re-render the existing 60 s walkthrough, or wants to upload/publish/store a rendered video (any video, narrated-explainer chapters included) on GitHub releases. For long narrated chapters replaying terminal output, use narrated-explainer instead.
argument-hint: "<example id, e.g. 000> [--slug name] | publish <video>"
---

# 60-second walkthrough video with live captures (HyperFrames)

Four 15-second acts: (1) the original Jenkinsfile running on the local Jenkins, (2) analyse / convert / validate,
(3) the differential trace comparison, (4) the converted workflow running on real GitHub Actions, then an outro. Acts 1
and 4 show **real runs**, filmed while they happen and cut to fit, inside a mock browser frame; acts 2 and 3 are
designed cards. The reference project is the examples/000 walkthrough (`assets/reference/`); a new video starts as a copy
of it and is adapted to its example.

Why it is built this way: a viewer trusts a migration demo when the runs on screen are real. So the clips are captured
from actual builds, every sped-up stretch is labelled, every number on screen traces to `source-facts.md`, and the text
around a clip must agree with what the clip shows (the 000 run turned out to have 11 jobs, not the 10 the earlier
screenshot-based video claimed; the left card's matrix and tarball version were also wrong and were fixed against the run).

## Rules (and why)

- **Film real runs; never fake a state.** If the run does something different from the script (a job count, a version,
  a skipped stage), the text changes, not the footage. Tell the user what differed.
- **Outward or costly actions need the user's approval for that exact action in this conversation**: a GitHub capture
  (`hfw capture gha` pushes a branch and creates a workflow run in the harness repo), `hfw publish --yes`, anything that
  spends Actions minutes (hosted runs are not supported here at all), deleting a Jenkins job the skill did not create.
  Local Jenkins captures are free and need no approval beyond the task.
- **The GitHub profile is a real signed-in browser.** It lives outside the repo (`~/.cache/j2gha-capture-profile`). The
  user signs in by hand (`hfw gh-login`); you never handle their credentials. Captures are read-only (non-GET requests
  aborted), start runs from the terminal, hide avatars, and never record the Actions list (other repos' names).
- **Label every speed-up** (speed badge in the frame) and mention cuts in the project README.
- **Narration changes need the user's approval and a listen.** You cannot hear the audio; say so in every report.
- **Nothing generated goes into git**: captures, clips, audio and renders live in the work dir. Finished videos are stored
  as GitHub release assets with `hfw publish`, only when the user asks. Do not commit unless asked.

## Layout

```
<project>/   docs/video/<slug>/            inputs, small, may be tracked: index.html, compositions/, edit.json,
                                           narration.json, source-facts.md, README.md (what depends on the capture)
<work>/      .cache/video/<slug>/          generated, gitignored:
               capture/jenkins|gha/        frames/*.jpg + timeline.json (+ j2gha.log)
               site/                       staged HyperFrames site; site/assets/clips/*.mp4 (+ .map.json), site/assets/audio/master.mp3
               audio/                      per-act narration WAVs (cached by text) + music.wav
               out/                        walkthrough.mp4, snapshots/, *.published.json
$HFW_HOME    ~/.cache/hyperframes-walkthrough   playwright-core 1.64.0, hyperframes 0.8.145 (pinned), chosen capture browser
$NX_HOME     ~/.cache/narrated-explainer        Kokoro runtime, shared with narrated-explainer
```

## Commands (`scripts/hfw`, relative to this skill directory)

| Command | Purpose |
|---|---|
| `hfw setup` | one-time runtime install, no sudo; narration also needs `narrated-explainer/scripts/nx setup` |
| `hfw init --project P [--from DIR]` | copy the reference project (or another project) as a starting point |
| `hfw gh-login [--check]` | user signs the GitHub capture profile in by hand / report account and repo access |
| `hfw capture jenkins --work W --jenkinsfile F --job NAME [--input K=V] [--approve LABEL]` | film a build of a self-contained Jenkinsfile, inputs answered on camera |
| `hfw capture jenkins --work W --harness NNN [--mode full\|trace]` | film the harness's own Jenkins run (`ex-NNN-<mode>`) |
| `hfw capture gha --work W --example NNN [--mode trace\|full]` | film a self-hosted `j2gha run` of the example (needs approval) |
| `hfw sheet SRC OUT.png t1,t2,...` | labelled contact sheet of a capture dir (source times) or a video |
| `hfw clips --project P --work W` | cut the captures per `edit.json`; prints every event's clip time |
| `hfw audio --project P --work W` | Kokoro narration + music + mix; fails if a line overruns its act |
| `hfw lint\|snapshot\|render --project P --work W [--at t,...] [--out NAME] [--resolution 4k]` | stage the site and run HyperFrames; `--resolution 4k` renders 3840x2160 (sharp text; use it for YouTube, with clips cut at 2x their on-screen size; slow: with software GL HyperFrames falls back to screenshot capture, 82 min for the 60 s video against 2.5 min at 1080p) |
| `hfw publish FILE --tag TAG [--name ASSET] [--yes]` | upload a video to a GitHub release (dry run without `--yes`) |

## Workflow

1. **Intake.** Which example (`examples/NNN`), slug (default `NNN-walkthrough-60s`), and whether the user wants live GitHub
   capture (needs approval) or only Jenkins. Default paths: project `docs/video/<slug>/`, work `.cache/video/<slug>/`.
2. **Setup** once: `hfw setup` (and `nx setup` for Kokoro). Check prerequisites the captures need: `uv run j2gha jenkins
   status` (start with `jenkins up`), runner images for GHA (`uv run j2gha docker build --only runner`), and
   `hfw gh-login --check` (if it fails, ask the user to run `hfw gh-login` and sign in themselves).
3. **Facts.** Read the example's README, `analysis/analysis.json` (complexity score, coverage), `gha/workflow.yml` (jobs),
   `gha/migration-report.md`, run records (`runs/*/result.json`: traces, verdicts). Write `source-facts.md` (claim, source,
   status). Decide how Jenkins will be filmed: own-job mode if the Jenkinsfile runs to completion here as it is (000 or a
   twin `1NN`), harness mode otherwise; if neither finishes, the twin skill (`jenkins-example-twin`) comes first.
4. **Project.** `hfw init --project docs/video/<slug>`; adapt act texts, cards and the outro to the example and its facts;
   draft `narration.json` (one sentence or two per act, about 12 s spoken; spell numbers and tool names for speech,
   `j-two-g-h-a`). Show the user the narration and the on-screen claims and wait for approval.
5. **Capture Jenkins.** `hfw capture jenkins ...` (see `references/capture-and-edit.md`); read `timeline.json` events;
   `hfw sheet` the capture to find blank frames and redirects.
6. **Capture GitHub Actions** (after approval for this run): `hfw capture gha --work W --example NNN`. Report the run, its
   conclusion, jobs and j2gha's verdict line; update facts (job count, run number, duration) from the capture.
7. **Cut.** Edit `edit.json`, `hfw clips`, then set the compositions' clip-driven times (URL steps, speed badges, zooms,
   counters, callouts) from the printed clip times; the project README lists what depends on the capture.
8. **Audio.** `hfw audio` (only changed acts regenerate). Any act that overruns fails: shorten the text.
9. **Check.** `hfw lint`, then `hfw snapshot --at ...` at each callout and transition (root times: act N starts at
   15·(N-1) s) and read the sheet: text agrees with the clip, nothing important cropped by a zoom, no empty-box glyphs
   (`references/hyperframes-notes.md`).
10. **Render** in the background: `hfw render ...` (~2.5 min). `hfw sheet` the result at a few times per act.
11. **Report**: file path, duration, size; what is live and how it was cut (speeds); facts that changed; what you did NOT
    check (how the narration sounds); open items. Offer `hfw publish` (dry run first) if the user wants it stored.

## Publish

`hfw publish .cache/video/<slug>/out/walkthrough.mp4 --tag videos --name <slug>.mp4` prints the plan (repo and its
visibility, release, asset, size, sha256, whether it replaces an asset); with `--yes` it creates the release as a
pre-release if needed and uploads, writing `<file>.published.json`. A private repo's release assets are private too. Use
one release (e.g. `videos`) as the store and distinct asset names per video and version.

## Captures in narrated explainers

narrated-explainer's `clip` scenes replay these captures inside its long chapters: `nx clips` cuts them with this skill's
`scripts/build-clip.mjs` and the same edit format. Keep that file's interface (`buildClip(capDir, outFile, spec)` and the
`.map.json` it writes) stable, or update `narrated-explainer/scripts/render/clips.mjs` with it. Both skills mask with
the spec's `mask` boxes (see `references/capture-and-edit.md`).

## Re-cut or re-render without new runs

Captures stay in the work dir: change `edit.json` or the compositions, then `hfw clips`, `hfw snapshot`, `hfw render`.
Only a narration change re-runs Kokoro, and only for the changed act.
