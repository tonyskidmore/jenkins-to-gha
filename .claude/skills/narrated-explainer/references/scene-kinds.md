# scenes.json reference

```
{
  "meta":     { title, chip, fps, width, height, voice{voice,lang_code,speed}, pronunciations, prompt, replayLabel, colour[], lineIcons },
  "captures": { "<id>": { "file": "captures/x.txt", "label": "Part 1 · what this shows" }, ... },
  "clips":    { "<name>": { "capture": "capture/jenkins", "trimStart", "trimEnd", "segments", "crop", "scale", "mask" }, ... },
  "scenes":   [ { id, kind, narration, source, ...kind fields }, ... ]
}
```

- Paths are relative to the scenes.json file. `chip` is the small header text (defaults to `title`).
- `prompt` is the shell prompt drawn before replayed commands (default `$ `). `replayLabel` is the honesty label in the
  terminal title bar (default "replay of real captured output"); keep it.
- `colour` overrides terminal line colouring: `[{ "match": "regex", "flags": "i", "tone": "ok|bad|warn" }]`; first match wins.
  Defaults colour errors red, warnings amber and success words green. `lineIcons: false` turns off the CSS tick/cross.
- `meta.allowedNames`: names `nx check` should not flag as possible leaks (the repo name, if it is the subject of the video; a
  name appearing in `meta.title` is exempt automatically).
- Every scene needs `id` (unique), `kind`, `narration` (except terminal scenes, whose narration lives in beats) and,
  strongly recommended, `source`: which doc section or capture backs its claims (the linter warns when missing; it is
  what makes fact-checking possible later).
- One unit of audio = one scene, or one beat of a terminal scene. Each unit is cached independently.

## Kinds

| kind | Fields | Looks like |
|---|---|---|
| `title` | `onScreen: [title, subtitle]`, `data.icon` (optional glyph) | big centred title |
| `disclaimer` | `onScreen: [heading, bullet, bullet...]`, `data.foot` | amber panel with bullets: use for "what this is and is not" |
| `explainer` | `onScreen: [ "text" or {"k": "label", "v": "text"} ... ]` (the field is `v`, not `text`) | grid of cards, revealed in order (k = small label above v) |
| `section` | `onScreen: [heading, subheading]` | chapter divider (also resets the header chip) |
| `summary` | `title`, `onScreen: [ "text" or {"text": "...", "tone": "warn"} ... ]` (the field is `text`) | ticked list; a `warn` item is highlighted as the caveat |
| `flow` chain | `data: {type:"chain", title, nodes:[{label, sub, bad}]}` | boxes joined by arrows, revealed in order |
| `flow` branch | `data: {type:"branch", title, question, yes:{label,text}, no:{label,text,bad}, note}` | a question with two outcomes |
| `filestack` | `data: {title, footnote, winLabel, loseLabel, readLabel, stages:[{label, files:[{name,value}], winner}]}` | ordered cards where the first one wins; use for any "first match wins" / precedence idea |
| `compare` | `data: {head:[...], rows:[[...],[...]]}` | table, rows revealed in order (first column is the row label) |
| `steps` | `data: {title, columns:[{title, items:[...]}]}` | numbered lists side by side, revealed across columns; use to explain what a command or function does |
| `cmdlist` | `data: {title, banner, items:[{cmd, note}]}` | commands shown, not run (set `banner` to say so) |
| `screenshot` | `data: {title, url, image, annotations:[{box:[x,y,w,h], label, tone}]}` | a real browser screenshot in a frame; annotation boxes (fractions 0..1 of the image) and callouts appear in order; `url` is the label shown in the address bar |
| `clip` | `data: {clip, url, title, start, hold, callouts:[{at, label, tone}], zoom:[{at, scale, origin, dur}]}` | live footage of a real run in a browser frame, speed label from the edit, callouts at capture events |
| `terminal` | `capture`, `part` (optional), `beats:[{steps:[i], narration, highlight:[...], clear, part, capture}]` | replayed terminal, one narration beat per command |

### Small details

- `respell` (pronunciations.json) replaces whole words, case-sensitively, before synthesis; `phonemes` entries match the
  same way. List each spelling you use ("GitHub" and "Github" are different entries).
- `explainer` items may mix plain strings and `{k, v}` objects. It is a two-column grid; up to 6 cards fit, more will crowd
  (split into two scenes). Cards are revealed in order across the narration.
- `cmdlist` shows each command and its `note`; keep the narration to what the commands are for (about 6 commands in 40 to 60
  words), the viewer reads the commands themselves.
- `summary` takes an optional `title` (default "Summary").

### Terminal scenes

- `steps` are zero-based indexes of commands in the capture file (`@@CMD@@` blocks in order). Use one beat per command, so
  every command gets its own explanation; use 2 to 3 steps in a beat only for trivial companions (e.g. `cd` + `ls`).
- Beats in a scene continue the same screen (older lines scroll up). A new scene starts a clean screen; `clear: true` on a
  beat starts a new screen mid-scene (e.g. a later stage); `part`/`capture` on a beat switch the header label/capture.
- `highlight` exists only in terminal scenes. Items appear on the right after the output: a string (neutral) or `{text, tone}` with tone `ok|bad|warn|info`.
  Say what the viewer should notice ("password missing from the offered list"), not what the command is.
- Timing is computed for you: commands type at about 40 characters per second, output appears line by line, and the
  narration is centred in the action if the action is longer.

### Screenshot scenes

For walkthroughs that click through a web UI. Capture the images with `nx shots --spec shots.json --out DIR` (puppeteer on
the system Chrome): the spec lists `{name, url, waitFor, clip, fullPage, hide, actions}` per shot, plus optional HTTP basic
`auth` sent only to the captured origins. Do the state changes (create, build, approve) with the tool's own API or CLI first;
shots only look. Then reference `DIR/<name>.png` from a `screenshot` scene.
- Logged-in sites (github.com): add `"profile": "/abs/path/outside/repo"` to the spec and run once with `nx shots --spec S --out D --login`
  to sign in (read-only account) in a headed window. Later runs reuse the profile headlessly and are read-only: non-GET
  requests are aborted and navigation stays on the shot origins. The profile is never read by Claude.
- Match picture to words: before using an image, check that it shows exactly what the narration claims (paused vs finished,
  before vs after, which build number). Capture transient states while they exist.
- Read every PNG before using it: pages half-loaded, showing tokens, usernames you must anonymise, or other users' data are
  common. Re-shoot with a longer `waitFor` or hide noisy elements (`hide: [css]`).
- Choose annotation boxes from the image you looked at, as fractions of its width and height. Aim at the thing the
  narration is about, one or two boxes per image, and say what to notice in `label`.
- Annotation `tone`: `info` (neutral, default), `ok`, `bad`, `warn` (colour and icon of the callout). The address-bar label
  is `data.url`; `part`/`meta.chip` work as for other scenes (screenshot scenes show the chip, not a part label).
- Long pages: use `clip` with y beyond the viewport (it captures beyond it) and `scroll` actions; `fullPage` is ignored
  when `clip` is given. Re-shoot only some images with `--only name1,name2`.
- A screenshot scene is held for its narration plus about 1.5 s; annotations appear evenly across the narration.
- One screenshot per scene; use several scenes in a row for a sequence. Prefer a `clip` that crops to the relevant part
  (browser chrome and empty areas shrink the useful pixels).
- The player shows the image at up to about 1300 by 700 pixels; small text in a full-page capture will be unreadable, so crop
  or capture at a smaller viewport width.

### Clip scenes (live footage)

For a run that is better watched than described (a pipeline's stages going green, a build pausing for approval). The
footage is a real screen recording, replayed frame by frame; nothing in it is drawn.

1. **Capture** with the hyperframes-walkthrough skill into this video's work dir: `hfw capture jenkins --work W ...` (local
   Jenkins, free) or `hfw capture gha --work W --example NNN` (pushes a branch and starts a workflow run: the user's approval
   for that exact run first). An existing capture can be reused by path, e.g. `"capture": "../000-walkthrough-60s/capture/jenkins"`.
2. **Cut** it in the top-level `clips` (same edit format as hfw's `edit.json`, see its references/capture-and-edit.md):
   `segments` play source seconds `a-b` at speed `x` (`"0-6.5:1,6.5-30:4"`); 20 to 50x is a cut. `crop`/`scale` fit the
   footage to the frame (about 1300 by 700 shown). Then `nx clips --script S --work W`: it prints every capture event with
   its clip time and extracts the frames into `W/clips/<name>/`.
3. **Anonymise** with `mask: [{box: [x, y, w, h], why}]` (fractions of the clip frame): filled boxes drawn into every frame.
   GitHub's run page shows who pushed, the run number and the commit; Jenkins shows the user who started a build. Read
   frames from the start, middle and end (`ls W/clips/<name>/`, open a few JPEGs) before using the clip.
4. **Write the scene.** Times in `data` are clip seconds or capture events: `"input-pending"`, `"job-completed:Publish"`
   (event plus its job, stage, name or message), `"#2"` for the second match. `url` is a string or `[{at, url}]` steps that
   follow the footage. `zoom` keys each ease from the previous scale to their own (`origin` carries over; `scale: 1` zooms
   out). `start` (default: when the narration starts) delays the footage, `hold` (default 1 s) keeps the last frame.

Rules the tools enforce or help with:
- The speed label in the frame's top bar comes from the edit itself: "▶ real time", "▶▶ 3× speed", "cut" for a moment at
  each cut, "■ last frame held" at the end. It cannot be switched off.
- Narration is not synchronised word by word. Line the footage up with `start`: find the key words in `W/audio/manifest.json`
  (`words[].start`, plus the 0.5 s lead) and the events printed by `nx clips`. `nx timeline` warns when the footage runs more
  than 2 s past the narration; `nx qa` reports the silence.
- Say in the narration what the viewer sees, and what is sped up; every number in a callout must be visible in the footage
  or come from the capture's timeline.json.
- Cost: every footage frame is a screenshot (about 0.1 s each), like a busy scene; a minute of footage adds about 3 to 4
  minutes of render time (less with `nx render --jobs 3`).

### Long captured text

There is no scrolling viewer for a 100-line file. Show the part that matters: capture it with a `grep`/`sed -n 'a,bp'`
command through `step`, so the viewer sees the exact command that trimmed it. Split a long output across beats.

### Showing only what is real

Terminal text comes only from captures (see SKILL.md, "Capture real output"). `cmdlist` and `steps` kinds show text you
write, so only put commands in `cmdlist` that really exist (copy them from the source doc), and say "shown, not run".

## Backlog (not implemented yet)

- Word-synchronised cues (commands typed when the narrator says them); timing is currently proportional.
