# HyperFrames notes (hyperframes 0.8.145)

The CLI's own docs are in `$HFW_HOME/node_modules/hyperframes/dist/docs/` (data attributes, compositions, GSAP,
rendering, troubleshooting) and its skills in `.../dist/skills/`. What mattered for this project:

- **Timed media is owned by the framework.** A `<video data-start data-duration data-media-start muted>` is decoded in
  sync with the render. HyperFrames forces `opacity: 1` on active timed elements, so never animate the `<video>`
  itself: wrap it in an untimed `<div>` (the "camera", e.g. `#jenkins-cam`) and animate the wrapper's transform/opacity.
- **Times inside a sub-composition are local.** `data-start="0.6"` in act 1 means 0.6 s into act 1. `hyperframes lint`
  warns `nested_media_start_basis_ambiguous` for any non-zero value: expected, leave it.
- **Timelines are seeked, not played.** Use `tl.to/fromTo/set` at absolute positions on the act's paused timeline
  (`window.__timelines["<id>"]`); no `setTimeout`, no callbacks that only fire during playback. A text change is
  `tl.set(el, { textContent: '3 / 11 jobs passed' }, t)`; seeking backwards restores the previous text.
- **Zoom/pan** = scale the camera wrapper with a `transformOrigin` chosen so what matters stays inside the frame (act 4
  anchors bottom-left, `0% 100%`, so all 11 jobs stay visible). Check the extremes with stills: a zoom that crops a
  graph's ends or a list's last item is worse than none.
- **No emoji in overlays you add**: the render machine may have no emoji font (⏩ rendered as an empty box). Use plain
  Unicode such as ▶ and ▶▶, which Inter and JetBrains Mono have.
- **Size the clip to the frame.** Act 4's body is 1216x450: crop the capture to that aspect and scale to exactly 1216
  wide, so `object-fit: cover` crops nothing. Act 1's 1280x690 capture is shown at 964x520.
- `hfw snapshot --at` takes ROOT times (act 4 starts at 45 s). Snapshots of video frames are exact; use them for every
  callout timing check before a full render.
- A full render of 60 s at 1080p takes about 2.5 minutes (3 workers, software GPU): run it in the background.
- External scripts/fonts come from jsdelivr (GSAP 3.14.2) and Google Fonts; the render needs network access for them.
