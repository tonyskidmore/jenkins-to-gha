---
name: narrated-explainer
description: Build a narrated explainer or walkthrough video from technical documentation, with no paid video framework. Writes a scene script, replays REAL captured terminal output and screen recordings of real runs, generates British or American female narration locally with Kokoro (no API key), burns in word-highlighted captions, and renders an mp4 with headless Chrome and ffmpeg. Use whenever the user wants a video, screencast, training video, tutorial video, narrated demo, explainer or voiceover for a README, walkthrough, runbook, issue write-up or CLI workflow, even if they never say "video skill" - for example "turn this walkthrough into a video", "make an educational video explaining this", "narrate these commands", "record a demo with a voiceover". Also use to extend, re-render or fix an existing explainer project (scenes.json, pronunciations, captures).
argument-hint: "<source doc or topic> [--chapter name] [--engine kokoro]"
disable-model-invocation: true
---

# Narrated explainer video

Turns a source document (a README walkthrough, a runbook, an issue analysis) into a short narrated video. The text
on screen that looks like terminal output is **replayed from real captures**, the voice is generated locally, and every
frame is rendered deterministically. Nothing needs a paid service or an API key.

Why it is built this way: viewers trust a technical video only if what they see actually happened, and a script that
sounds more certain than its source doc misleads people. So the workflow forces real captures, source pointers for every
scene, a plain statement of limits, and an honest report of what was and was not checked (nobody has listened to the audio
until a person does).

## Rules (and why)

- **Capture real output; never invent or tidy it.** Run the commands with `nx capture`. If reality differs from what the
  doc promises, that is a finding to tell the user about.
- **No costly or outward actions to produce a capture** (anything that spends money or quota, pushes to a remote, sends a
  message, or needs sudo) unless the user approved that exact action in this conversation. Reuse results already on disk
  or run only the local, free path. Approval for one run is not approval for the next.
- **Never read, print or commit `.env` files, tokens or API keys.** This skill needs none. Redact captures (below).
- **Stay inside the source.** Each scene's `source` names the doc section or capture behind it. Keep the source's caveats
  and its "not done / needs acceptance" statements; the summary must carry them.
- **Anonymise** unless told otherwise: no host names, customers, people, tickets, account or repo owner names, run ids.
- **Get the user's approval of the script before generating audio**, and ask them to listen to the voice and judge
  pronunciations: you cannot hear it. Say so in your report.
- **Do not commit** anything unless asked. Generated output stays out of git.

## Layout

Two directories per video (a "chapter" is just a separate pair):

```
<project>/     inputs you author; small; the user may choose to track these (e.g. docs/video/<slug>/)
  scenes.json            the script (schema: references/scene-kinds.md)
  pronunciations.json    {"phonemes": {term: kokoro-phonemes}, "respell": {term: plain respelling}}
  captures/*.txt         REAL command output (made by nx capture)
  source-facts.md        safe claims with pointers + "do not claim" list (recommended)
<work>/        generated; gitignored (e.g. .cache/video/<slug>/)
  audio/  timeline.json  out/video.mp4  out/sheet.png  out/qa-report.json
  capture/<name>/  clips/<name>.mp4 + <name>/*.jpg   live footage for clip scenes (hfw capture, nx clips)
$NX_HOME       runtime (Kokoro venv, puppeteer-core), default ~/.cache/narrated-explainer, shared, outside any repo
```

If the user has not said where to put things, propose `<repo>/docs/video/<slug>/` for the project (untracked until they
say otherwise) and `<repo>/.cache/video/<slug>/` for the work dir, after checking `.gitignore` covers the work dir.

## Commands (`scripts/nx`, relative to this skill directory)

| Command | Purpose |
|---|---|
| `nx setup` | one-time runtime install; no sudo; prints what is missing |
| `nx check --script S [--work W]` | lint the script (needs only node, no setup): unknown kinds, bad capture indexes and item shapes, TTS-unfriendly words, missing sources, non-zero captured commands, estimated video length, work dir not git-ignored |
| `nx shots --spec S --out DIR` | real browser screenshots of a web UI for `screenshot` scenes (see references/scene-kinds.md) |
| `nx capture local OUT SCRIPT` / `nx capture docker IMAGE OUT SCRIPT [docker flags]` | record real output (see below) |
| `nx audio --script S --work W [--force] [--only ID]` | narration + word timestamps; cached; audits dropped words |
| `nx clips --script S --work W [--only NAME]` | cut the live-footage clips in the script's `clips` from hfw captures and extract their frames (clip scenes) |
| `nx timeline --script S --work W` | combine audio, captures, clips and script into `timeline.json` |
| `nx render --work W [--stills t1,t2] [--jobs N] [--scale 2] [--out NAME]` | `out/video.mp4`, or PNG stills for checking layout; `--jobs 3` renders slices in parallel (about 2x faster on 8 cores); `--scale 2` draws at 2x pixel density for a 3840x2160 video (sharp text; use it for YouTube uploads; with `--jobs 3` it took 3 to 3.6 times the chapter length, while another render shared the CPU) |
| `nx concat OUT.mp4 CH1.mp4 CH2.mp4 ...` | join the chapter videos of a series into one movie (lossless; they must come from this pipeline) |
| `nx qa --work W` | duration, loudness, silent gaps, contact sheet of the whole video |

## Workflow

1. **Intake.** Establish the source doc, audience (default: mixed technical and non-technical), target length, chapters
   (an hour-long walkthrough should become several 3 to 6 minute videos), and where files go. Voice default: Kokoro
   `bf_emma`, British female. Ask only what you cannot infer.
2. **Setup** once: `scripts/nx setup`. If tools are missing it tells you; installing system packages needs the user.
3. **Read the whole source doc** (not a summary), plus anything it links that the video will claim. Write
   `source-facts.md`: safe claims with section pointers, and what not to claim. Decide what the video is *not* and what
   limits to state. **Scope a chapter honestly:** if its steps depend on earlier ones (a service started in Part 1, an
   image built earlier), say so in the opening note and, if you will not show them, tell the viewer what is assumed.
4. **Capture real output.** Write a capture script of `step '<command>'` lines and run `nx capture`. For a disposable
   container use `nx capture docker <image> ...` with the flags the doc uses (e.g. `--network none --entrypoint bash`).
   - *Quoting trap:* `step` runs its argument through `eval` inside a shell script, so `$`, quotes and backslashes are
     interpreted twice. Wrap each command in single quotes, double any inner single quotes as `'\''`, or put awkward
     commands in a small script file and `step 'bash ./that.sh'`. `nx capture` prints each command's exit code: read every
     non-zero line (a failing command is valid content; a quoting slip such as `sed: unexpected ','` is not) and re-run.
   - *Showing a file, not just a command's output:* run it through `step` (`step 'sed -n 1,12p path'`, `step 'grep -n
     pattern path'`). The text on screen is then genuinely that command's output, and trimming is your choice of grep or
     sed range, which the viewer can see. `cmdlist` and `steps` scenes are text you wrote, not captures.
   - *Redaction and approvals:* set `NX_REDACT` BEFORE the first capture, and run an approved command only under `nx capture`
     (never once bare and again inside capture: a second run is a second action, and for costly or outward commands the
     user approved one). If something slipped through, `nx capture redact FILE` rewrites an existing capture.
   - *Pipes hide failures:* in `step 'a | b'` the exit code is that of `b`. Put `set -o pipefail` on a silent line at the top
     of the capture script. A tool that returns 0 even when its verdict is bad (a comparison that reports "differs") will
     not show up as a non-zero exit: read the output, not just the code.
   - *Chapters that change state:* when a demo edits something and restores it, capture a read-only check before, after the
     change and after the restore (a `grep` of the changed line), and verify the repo or system is back as found before you
     report. Say in the narration that the change is deliberate and undone.
   - *Capture scripts are sourced, not executed:* `$0` and `dirname "$0"` are not the script's path; use absolute or
     repo-relative paths. Use a subshell for directory changes, `( cd dir && cmd )`, because a bare `cd` in one step
     persists into every later step.
   - *Steps share one shell:* all `step` lines of a capture script run in the same shell, so variables, `cd` and functions
     persist between them. Use silent setup lines (plain commands, not `step`) to define variables or a helper function that
     shortens long commands, but keep the shown command honest: say in the narration what a helper does. Short silent variables are also the fix for
     `nx check`'s "command over 100 characters" warning.
   - *Web UIs:* make the state changes with the app's API or CLI (only actions the user approved), then capture pages with
     `nx shots --spec captures/shots.json --out shots`. Credentials are sent as an Authorization header only to the captured
     origins; never capture a login page or a page that shows a token, and read every PNG. **Shoot state-dependent screens at
     the moment they exist** (a build paused for approval, an error before it is fixed), not in one batch at the end: a
     batch taken afterwards shows the finished state and the narration then describes a picture that is not there. For each
     image, compare what you see with the sentence that will be spoken over it. If the state is gone, recreate it (for
     example by repeating the action) and say so in the narration ("the same build run again"). Annotation boxes are fractions of
     the (clipped) image. See references/scene-kinds.md, "Screenshot scenes".
   - *Keep the capture scripts:* save them next to the captures (`captures/<name>.sh`, with the `nx capture` line that
     runs them in a comment) so the captures can be reproduced after the source or tool changes.
   - *Live footage of a run* (a build going green, a pause for approval) is a `clip` scene: film it with the
     hyperframes-walkthrough skill (`hfw capture jenkins|gha --work <this work dir>`; a GitHub capture pushes a branch and
     starts a run, so it needs the user's approval for that run), cut and mask it in `clips`, then `nx clips`. Mask every
     account name, run number and commit id the page shows. See references/scene-kinds.md, "Clip scenes".
   - *Fit the screen:* about 70 characters per line and 16 lines fit. Wide tables and long files need a command that picks
     columns or a line range (`awk -F'|'`, `cut`, `sed -n 'a,bp'`). The machine may have no emoji font, so emoji in output
     draw as empty boxes: choose a command that avoids them. `nx check` warns about both.
   - *The doc's "Expected" text is a claim, not a capture.* Compare it with the real output and list every difference
     for the user (a stale README is a useful finding; do not edit the doc unless asked). The video uses the real output and
     does not comment on the doc's mistakes (see references/narration-and-honesty.md).
   - Redaction: set `NX_REDACT=<absolute path>` to a file of `regex=>replacement` lines (sed -E, top to bottom: specific
     rules such as paths before general ones such as the owner name) before capturing, then read the capture files for names,
     tokens and ids before use. **Keep that file outside the project folder** (e.g. in the work dir): it contains the very
     strings you are hiding. Capture scripts must not hard-code home paths: start them with `cd "$(git rev-parse --show-toplevel)"`.
     `nx check` scans the script, captures and capture scripts for home paths, tokens, emails and your git owner/repo/user name.
     Plan pipes (`cut`, `awk`) for wide output in the FIRST approved command: an approved command cannot be reshaped later. The format and caveats are in `scripts/step.sh`, `capture.sh`.
5. **Write `scenes.json` and `pronunciations.json`.** Start from `assets/example/`. Follow
   `references/narration-and-honesty.md`: plain-language narration, detail on screen, one command per beat, an opening
   note on what the video is and is not, a closing summary that repeats the limits. Run `nx check --script ... --work ...` and fix errors; heed warnings. Rules of thumb: a chapter under about 3 minutes is probably thin (say so if it is deliberate), terminal beats under about 45 words,
   other scenes under about 90, finished video about 1.2 times the speech time, 3 to 6 minutes per chapter.
6. **Show the user the script** (scene list, what each says, anything you had to judge) and wait for approval.
7. **Audio.** `nx audio ...`. Every "no phonemes" warning is a word that would be silently dropped: respell it or give it
   phonemes, re-run (only changed units regenerate). Ask the user to listen to the first clips and approve pronunciations of
   product and acronym terms; record approvals in `pronunciations.json`.
8. **Timeline, stills, render.** `nx clips` if the script has clip scenes, `nx timeline`, then `nx render --stills ...` at one
   time per scene kind (and at each callout of a clip) and read the PNGs. Fix layout problems (overflowing text, late-appearing
   items, empty panels, footage out of step with the narration). Then run `nx render --jobs 3` in the background (about 5
   minutes for 5 minutes of video; one job takes about twice as long) and poll its log. Do not sit in a blocking wait.
9. **QA and report.** `nx qa`; read `out/sheet.png`. Fix long silences and anything visibly wrong; re-render if needed.
   Report: the file path, duration, what you checked (frames, contact sheet, loudness, silences, dictionary audit,
   captures match the doc), what you did **not** (how it sounds, pacing), real findings from the captures, and open items.

## Edit and re-render

For a small change (a pronunciation, a sentence, an annotation) do not start over:
1. Find what the change touches: `grep -n "word" scenes.json`. Edit `pronunciations.json` (term-wide) or `scenes.json`.
2. `nx check`, then `nx audio`: the cache key is the spoken text after substitution, so only units whose spoken text changed
   are regenerated (the output lists `generated ...`; everything else is cached). Read any "no phonemes" warning: a respell
   to short fragments (such as "un stash") needs phonemes for those fragments.
3. `nx timeline`, `nx render --work W` in the background, `nx qa`. No capture is re-run and `nx setup` is not repeated.
4. Tell the user which clip and time to listen to (the word timestamps are in `audio/manifest.json`: `words[].text/start/end`),
   and record their approval in `pronunciations.json`. You cannot hear it.
Poll a background render with `until grep -q "^wrote" render.log; do sleep 5; done` (with a timeout), not a long sleep.

## Short overviews without captures

Not every video replays a terminal. For a quick overview of a README section, skip the capture, redaction and screenshot
steps: use `"captures": {}`, the `explainer`, `compare`, `steps`, `cmdlist`, `flow` and `summary` kinds, and show commands with
`cmdlist` and a banner saying "Shown, not run" (copy them from the source; run none that need credentials, network pushes, sudo
or change local state). Say so in the opening note and the summary. **The user's requested length wins** over the 3 to 6
minute rule of thumb: 1.5 to 2 minutes is a fine overview. The steps that still apply are reading the source in full, the
source-facts file, the script, `nx check`, approval, audio with its audit, stills, render, and QA.

## When something goes wrong

- Kokoro install errors, espeak crashes, dropped words, odd pronunciations: `references/kokoro-and-render-notes.md`.
- A scene looks wrong: `references/scene-kinds.md` has every field; fix the data first, the player only if a kind
  genuinely cannot express the idea (then add a kind, keep it data-driven, and note it in the reference).
- The capture shows something different from the doc: tell the user, quote the real output, and let them decide whether
  the video or the doc should change.
- A long silence between lines: usually a terminal beat whose typing outlasts its narration; split the beat or shorten
  the command in the script (never edit captured text).

## Not supported yet (ask the user before building)

Interactive UI automation inside the tool (screenshots and replayed screen recordings are supported; driving the UI through forms is not: use the app's API or CLI for state changes, or hfw capture for a filmed run), word-synchronised command and footage cues, other voices or
engines (ElevenLabs was considered; Kokoro was chosen to avoid keys and licence questions), subtitles files, music.
