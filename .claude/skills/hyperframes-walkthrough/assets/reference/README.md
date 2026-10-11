# 60 s walkthrough project (HyperFrames)

Inputs for one walkthrough video, made with the `hyperframes-walkthrough` skill (`.claude/skills/hyperframes-walkthrough/`).
Generated media (captures, clips, audio, renders) live in the work dir, never here.

| File | What |
|---|---|
| `index.html` | root composition: HUD, act stepper, the four acts, master audio (`assets/audio/master.mp3`) |
| `compositions/act1-jenkins-baseline.html` | act 1: live Jenkins clip (`assets/clips/jenkins_run.mp4`) in a browser frame + pipeline card |
| `compositions/act2-analyze-convert.html` | act 2: analyse / convert / validate pillars (static) |
| `compositions/act3-differential-traces.html` | act 3: trace comparison and scorecard (static) |
| `compositions/act4-github-actions.html` | act 4: live GitHub Actions clip (`assets/clips/gha_run.mp4`) + scorecard, then the outro |
| `edit.json` | how each capture is cut into its clip (`hfw clips`) |
| `narration.json` | the spoken text and timing per act (`hfw audio`) |
| `source-facts.md` | every on-screen claim with its source and status |

## What depends on the capture

A new capture changes timings and facts. After `hfw capture ...` and `hfw clips ...`:

- `edit.json`: cut points (find them with `hfw sheet` on the capture dir).
- Act 1 GSAP times: composition time = 0.6 + clip time (URL steps, speed badge, zooms, gate pill, approval callout,
  completion banner). Build number in the banner.
- Act 4: the run URL in the URL bar, the job count (text and counter), the `tl.set(... textContent ...)` counter times
  (= 0.5 + each `job-completed` clip time) and the run-completed time.
- `source-facts.md`: re-verify every row marked verified.
