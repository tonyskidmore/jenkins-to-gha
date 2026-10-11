# Capturing live runs and cutting them into clips

## Jenkins (`hfw capture jenkins`)

- **Own-job mode** (`--jenkinsfile F --job NAME`): for a pipeline that runs to completion on the local controller as it
  is (`examples/000`, a twin `examples/1NN`). The job is recreated so the run is build #1. Inputs are answered on camera:
  `--input NAME=VALUE` types each parameter (located by the parameter's hidden `name` field), `--approve LABEL` picks the
  button (`Deploy` in 000; default is the form's `proceed` button). Parameterised *jobs* (a `parameters {}` block whose
  first build needs values) cannot be triggered with `/build`: the first build of a new job uses the defaults, which is
  what 000 relies on.
- **Harness mode** (`--harness NNN --mode full|trace`): films `j2gha run NNN --tier jenkins` (job `ex-NNN-<mode>`). Works
  for any example the harness can run; the harness approves inputs itself (`proceedEmpty`), so there is no on-camera
  approval. It writes the example's normal run record (`examples/NNN/runs/jenkins-<mode>/`).
- The recording is a CDP screencast of the Pipeline Overview (`/job/J/N/stages`): one frame per repaint, CSS-pixel size
  (the viewport, default 1280x690 for a 964x520 browser body). It does not honour deviceScaleFactor.
- Known moments that need cutting: the blank stages page while Jenkins starts the build (several seconds before the
  graph appears), Jenkins' redirect to the console page after an input is submitted, page reloads.

## GitHub Actions (`hfw capture gha`)

- Self-hosted tier only (JIT runner containers on this machine, 0 billable minutes; `j2gha docker build --only runner`
  first). It still pushes an orphan `j2gha/run/...` branch (deleted afterwards) and creates a workflow run in the
  harness repo: get the user's approval for each capture run. Hosted runs spend minutes: not supported here.
- Needs the signed-in profile (`hfw gh-login`, check with `hfw gh-login --check`). If it is the user's main account the
  read-only guard matters: every non-GET request is aborted (GitHub's telemetry POSTs are the only ones normally seen).
- Frames are `Page.captureScreenshot` with `clip.scale = 2` (3200x1208 for the 1600x604 region), ~3.5 fps. That clip
  region holds the title, the job list, the summary (status, total duration) and the graph. The graph's node labels are
  too small to read at video size; the job list is the readable part, so zoom on it, not on the graph.
- Never record the Actions list: it shows other runs and other repositories' names. Recording starts on the run page.
- The run page still shows who pushed (account name), the run number and the commit id. Mask them in `edit.json`
  (`"mask": [{"box": [x, y, w, h], "why": "account name"}]`, fractions of the cropped, scaled frame; `build-clip.mjs`
  fills each box in every frame), check a few frames with `hfw sheet` on the clip, and keep the URL bar text generic
  (`github.com/<owner>/<repo>/actions/runs/<run>`).
- Job transitions come from `gh api` polling every 2 s: event times can be up to 2 s late in source time.
- The run page already shows the final Success state when the run completes; the final reload is only a fallback and
  its blank frames must be cut.

## Choosing cut points

1. `hfw sheet W/capture/<name> /tmp/sheet.png 1,2,3,...` at a coarse step, then finer around transitions. Look for
   blank or half-drawn frames, redirects, and the first frame where each state is visible.
2. Write segments in `edit.json`: real time (1x) for moments the narration or callouts point at, 3x to 15x for progress,
   20-50x for cuts (shorter than one output frame). Every stretch that is not 1x must be labelled on screen (speed
   badge), and cuts mentioned in the project README.
3. `hfw clips` prints each event's clip time; the clip's total must fit the window the composition gives it (act 1: 14.4
   s from 0.6 s; act 4: 9.5 s from 0.5 s, before the outro at 10 s).
4. Set the composition's GSAP times from those clip times (+ the video's `data-start`), then `hfw snapshot` at the
   moments that matter and read the stills.
