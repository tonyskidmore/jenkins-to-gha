"""Per-unit narration with Kokoro + per-word timestamps.

Usage: $NX_HOME/.venv/bin/python generate.py --script SCENES.json --work WORKDIR [--force] [--only ID ...]
  (normally run through `nx audio ...`)

Input : scenes.json. A scene with "beats" yields units "<id>.1", "<id>.2", ...; otherwise "<id>" (if it has "narration").
        meta.voice = {"voice": "bf_emma", "lang_code": "b", "speed": 1.0}   (lang_code: a=American, b=British)
        pronunciations file (meta.pronunciations, default pronunciations.json next to scenes.json):
          {"phonemes": {"SSH": "..."},  "respell": {"Ansible": "Ansibul"}}
          phonemes = Kokoro/misaki phoneme strings, injected as [word](/phonemes/). Must match the lang_code's set
                     (British uses Q for the "oh" diphthong and long vowels with a length mark; American differs).
          respell  = plain-text substitutions applied before synthesis (e.g. to say "re-creation" not "rec-reation").
          Order: respell is applied FIRST, then phonemes are matched against the respelled text. So a respell may need
          phonemes for its own fragments ("unstash" -> "un stash" needs a phoneme for "un", which Kokoro's dictionary lacks).
Output: WORKDIR/audio/<unit>.wav and WORKDIR/audio/manifest.json
        {unit: {file, durationSec, hash, words:[{text,start,end}]}}   (word times in seconds from clip start)
Cache : a unit is skipped when sha256(voice, speed, spoken text) is unchanged, so editing one pronunciation only
        regenerates the units whose spoken text changed. The manifest is saved after every unit (resumable).
Audit : prints every narration word with no phonemes. With the espeak fallback disabled (see below) such words are
        DROPPED SILENTLY by Kokoro, so each one must be respelled or given phonemes.
espeak: the espeak-ng bundled by `espeakng-loader` calls exit() on some Linux builds, which Kokoro cannot catch. We
        disable the fallback before importing kokoro; out-of-dictionary words then need phonemes/respelling (above).
"""
import argparse, hashlib, json, pathlib, re, warnings
warnings.filterwarnings("ignore")          # torch/kokoro deprecation noise hides the useful 'generated'/'WARNING' lines
import numpy as np, soundfile as sf
from misaki import espeak, en

def _off(*a, **k):
    raise RuntimeError("espeak disabled (bundled build can exit the process)")
espeak.EspeakFallback = _off          # must be set before importing kokoro
from kokoro import KPipeline

SR = 24000

def load_pron(script_path, meta):
    p = pathlib.Path(meta.get("pronunciations") or "pronunciations.json")
    p = p if p.is_absolute() else script_path.parent / p
    if not p.exists():
        return {}, {}
    d = json.loads(p.read_text())
    return d.get("phonemes", {}), d.get("respell", {})

def mark(text, phonemes, respell):
    for term, new in respell.items():
        text = re.sub(rf"(?<![\w-]){re.escape(term)}(?![\w-])", new, text)
    for term, ph in phonemes.items():
        text = re.sub(rf"(?<![\w\[/-]){re.escape(term)}(?![\w\]/-])", f"[{term}](/{ph}/)", text)
    return text

def units(data):
    for s in data["scenes"]:
        if s.get("beats"):
            for k, b in enumerate(s["beats"]):
                yield f"{s['id']}.{k + 1}", b["narration"]
        elif s.get("narration"):
            yield s["id"], s["narration"]

def trim_tail(a, keep=0.18, floor=0.3):
    """Drop trailing near-silence (Kokoro pads clips); keep a short natural tail."""
    idx = np.where(np.abs(a) > 0.01)[0]
    end = (idx[-1] + int(keep * SR)) if len(idx) else len(a)
    return a[: max(int(floor * SR), min(len(a), end))]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True); ap.add_argument("--work", required=True)
    ap.add_argument("--force", action="store_true"); ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    script_path = pathlib.Path(a.script).resolve()
    data = json.loads(script_path.read_text())
    v = data.get("meta", {}).get("voice", {})
    voice, lang, speed = v.get("voice", "bf_emma"), v.get("lang_code", "b"), float(v.get("speed", 1.0))
    phonemes, respell = load_pron(script_path, data.get("meta", {}))
    audio_dir = pathlib.Path(a.work) / "audio"; audio_dir.mkdir(parents=True, exist_ok=True)
    mf_path = audio_dir / "manifest.json"
    manifest = json.loads(mf_path.read_text()) if mf_path.exists() else {}

    g = en.G2P(trf=False, british=(lang == "b"), fallback=None, unk="")
    pipe, made, flagged = None, 0, {}
    for uid, narration in units(data):
        if a.only and uid not in a.only and uid.split(".")[0] not in a.only:
            continue
        text = mark(narration, phonemes, respell)
        h = hashlib.sha256(json.dumps([voice, speed, text, "trim1"], ensure_ascii=False).encode()).hexdigest()[:16]
        if not a.force and manifest.get(uid, {}).get("hash") == h and (audio_dir / f"{uid}.wav").exists():
            continue
        spoken = re.sub(r"\[[^\]]*\]\(/[^)]*/\)", " ", text)           # words already given phonemes are fine
        empty = [w for w in sorted(set(re.findall(r"[A-Za-z][A-Za-z'-]*", spoken))) if not g(w)[0].strip()]
        if empty:
            flagged[uid] = empty
            print(f"  WARNING {uid}: words with no phonemes (Kokoro would drop them): {empty}")
        pipe = pipe or KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
        chunks, words, off = [], [], 0.0
        for r in pipe(text, voice=voice, speed=speed):
            arr = np.asarray(r.audio); chunks.append(arr)
            for t in (r.tokens or []):
                if t.start_ts is not None and t.end_ts is not None and re.search(r"\w", t.text):
                    words.append({"text": t.text, "start": round(off + t.start_ts, 3), "end": round(off + t.end_ts, 3)})
            off += len(arr) / SR
        audio = trim_tail(np.concatenate(chunks))
        sf.write(audio_dir / f"{uid}.wav", audio, SR)
        manifest[uid] = {"file": f"{uid}.wav", "durationSec": round(len(audio) / SR, 3), "hash": h, "words": words}
        made += 1
        print(f"generated {uid}: {len(audio)/SR:.1f}s, {len(words)} words")
        mf_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"done: {made} generated, rest cached" + (f"; {len(flagged)} unit(s) have dropped words: fix and re-run" if flagged else ""))

if __name__ == "__main__":
    main()
