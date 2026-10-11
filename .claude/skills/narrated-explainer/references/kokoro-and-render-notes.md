# Kokoro and rendering: things that bit us

## Kokoro (local text-to-speech, Apache-2.0 code; check the licence of the weights and voices before publishing)

- Voices: `bf_*` British female, `af_*` American female (`lang_code` `b` / `a`). Pair the voice with the matching
  `lang_code`: a British voice on the American text processor sounds American. `bf_emma` was the user's choice.
- Phoneme strings are per language. British uses `Q` for the "oh" diphthong and ends long vowels with a length mark;
  American differs. `A` = "ay", `I` = "eye", `W` = "ow", `Y` = "oy" in both. Get a starting point by phonemising a
  similar dictionary word and editing it; confirm by ear (ask the user).
- Out-of-dictionary words are dropped silently once the espeak fallback is off (see below). The audit in
  `generate.py` lists them. Fix with `phonemes` (exact sounds) or `respell` (plain text).
- Pronunciation precedence: `respell` is applied first, then `phonemes` match the respelled text (whole words,
  case-sensitive). A respell into short fragments ("un stash") fails silently unless each fragment is in Kokoro's dictionary
  or has a `phonemes` entry; the audit warning is the signal.
- Word timestamps are real (per word, seconds). Punctuation tokens have none, which is why captions take their words
  from the narration text when the counts match.
- Speed: roughly real-time on an 8-core CPU; no GPU needed. A 9-minute video takes about as long to synthesise.
- Weights (hexgrad/Kokoro-82M) and a small spaCy model download on first use. Offline machines must pre-seed the caches.
- Trailing silence per clip is trimmed (`trim_tail`); clips are cached per spoken text.

### Install gotchas (handled by `nx setup`)

1. Install `torch` first from the CPU index, separately. Mixing indexes in one resolve makes the resolver pick
   transformers 4.12 and fail compiling tokenizers (needs a Rust compiler).
2. Pin `transformers>=4.45`.
3. The espeak-ng bundled in `espeakng-loader` hard-codes a build path on some Linux builds and calls `exit()`, which Kokoro
   cannot catch (it only catches exceptions). `generate.py` disables the fallback before importing kokoro. The proper fix
   is the system package (`sudo apt install espeak-ng`), which only the user can run; the workaround needs nothing.

## Rendering

- Chrome headless via puppeteer-core and the system Chrome (no browser download). `--no-sandbox` is passed; it was needed
  on WSL2 or at least harmless. Snap Chromium may not work with puppeteer: prefer google-chrome.
- Every frame is a pure function of time and unchanged frames are not re-captured: about 27 fps effective, so a 9-minute
  video renders in about 10 minutes. Run the render in the background and poll its log; do not block on it.
- `--jobs N` splits the frames into N slices, each rendered by its own Chrome, joined losslessly and muxed once. Measured on 8
  cores: a 3.6-minute chapter took 339 s with one job and 162 s with three; four were no faster. Slices are not
  byte-identical to a one-job render (at least 48 dB PSNR per frame against it, which looks the same); two one-job renders
  of the same timeline differ too (at least 53 dB).
- Clip scenes show one pre-extracted JPEG per frame (`nx clips`), so footage is as deterministic as the rest. Seeking a
  `<video>` element per frame was measured and rejected: 30% slower and it depends on Chrome's decoder.
- HyperFrames (the hyperframes-walkthrough skill's renderer) was measured as a backend for this player and not adopted:
  slower on a whole chapter (it captures every frame; this renderer skips unchanged ones), a different Chrome build (text
  anti-aliasing differs), and it needs an undocumented runtime hook to drive player.js.
- Audio: each unit's wav is padded and concatenated, then `loudnorm` to about -16 LUFS in the final mux.
- Flex containers swallow spaces between inline spans: caption words are wrapped in one inner span (already done).
- Terminal lines wrap at about 70 characters at the default size. Long commands wrap; that is fine, but the line
  must remain the captured text.

## Look at frames, not just logs

`nx render --stills 12,40,95` writes PNGs; read them to check layout. `nx qa` writes a contact sheet of the whole video:
one image read shows every part. Do this before telling the user it is done. Fix what you can see (overflow, empty
panels, overlapping text, things that appear late) and re-render.
