"""hfw audio --project P --work W [--force]

Narration + music for a walkthrough, from P/narration.json:

    {"voice": "bf_emma", "lang": "b", "speed": 1.0, "duration": 60, "voiceVolume": 1.3,
     "music": {"volume": 0.28},                       # or null for no music
     "acts": [{"id": "act1", "start": 0.8, "end": 15, "text": "..."}, ...]}

Each act is synthesised with Kokoro (narrated-explainer's runtime) into W/audio/<id>-<hash>.wav, cached by the spoken
text, voice and speed; the music bed (a generated ambient arpeggio, one chord per act) goes to W/audio/music.wav; the
mix (narration delayed to each act's start, music under it, fade-out) to W/site/assets/audio/master.mp3, which the
root composition plays. Kokoro's inline phoneme markup works in the text: [pipelines](/pˈIplˈInz/).
Reports each act's length and fails if a line runs past its act's end: shorten the text, never speed up the voice.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SR_VOICE = 24000
SR_MUSIC = 44100


def synth(acts, cfg, audio_dir, force):
    from kokoro import KPipeline
    pipe = None
    out = {}
    for act in acts:
        key = hashlib.sha256(json.dumps([act["text"], cfg["voice"], cfg["speed"]]).encode()).hexdigest()[:12]
        wav = audio_dir / f"{act['id']}-{key}.wav"
        if force or not wav.exists():
            pipe = pipe or KPipeline(lang_code=cfg["lang"])
            chunks = [a for _, _, a in pipe(act["text"], voice=cfg["voice"], speed=cfg["speed"])]
            sf.write(wav, np.concatenate(chunks), SR_VOICE)
            print(f"  generated {wav.name}")
        else:
            print(f"  cached    {wav.name}")
        out[act["id"]] = wav
    return out


def music(acts, duration, path):
    """Ambient bed: per act a bass note plus an eighth-note arpeggio (Dm, Bb, Gm, D, cycling), slow pad, fades."""
    t = np.arange(int(SR_MUSIC * duration)) / SR_MUSIC
    bass = [146.83, 116.54, 98.00, 146.83]
    arps = [[220.0, 261.63, 329.63, 440.0, 523.25, 440.0, 329.63, 261.63],
            [233.08, 293.66, 349.23, 466.16, 587.33, 466.16, 349.23, 293.66],
            [196.0, 233.08, 293.66, 392.0, 466.16, 392.0, 293.66, 233.08],
            [220.0, 293.66, 369.99, 440.0, 587.33, 440.0, 369.99, 293.66]]
    note = 0.15625
    bounds = [a["start"] if i else 0.0 for i, a in enumerate(acts)] + [duration]
    audio = np.zeros_like(t)
    for i in range(len(acts)):
        m = (t >= bounds[i]) & (t < bounds[i + 1])
        fb, scale = bass[i % 4], np.array(arps[i % 4])
        tm = t[m]
        audio[m] += 0.22 * np.sin(2 * np.pi * fb * tm) + 0.08 * np.sin(4 * np.pi * fb * tm)
        f = scale[(tm / note).astype(int) % len(scale)]
        env = np.exp(-((tm % note) / 0.09))
        audio[m] += (0.15 * np.sin(2 * np.pi * f * tm) + 0.05 * np.sin(4 * np.pi * f * tm)) * env
    pad = 0.10 * (np.sin(2 * np.pi * 220 * t) + np.sin(2 * np.pi * 261.63 * t) + np.sin(2 * np.pi * 329.63 * t))
    audio += pad * 0.5 * (1 + np.sin(2 * np.pi * 0.1 * t))
    audio *= np.clip(t / 1.5, 0, 1) * np.clip((duration - t) / 2.0, 0, 1)
    audio = audio / (np.max(np.abs(audio)) + 1e-6) * 0.40
    sf.write(path, (audio * 32767).astype(np.int16), SR_MUSIC)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    cfg = {"voice": "bf_emma", "lang": "b", "speed": 1.0, "duration": 60, "voiceVolume": 1.3, "music": {"volume": 0.28}}
    cfg.update(json.loads((Path(a.project) / "narration.json").read_text()))
    acts = cfg["acts"]
    work = Path(a.work)
    audio_dir = work / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    master = work / "site" / "assets" / "audio" / "master.mp3"
    master.parent.mkdir(parents=True, exist_ok=True)

    print(f"[audio] Kokoro {cfg['voice']} x{cfg['speed']}")
    wavs = synth(acts, cfg, audio_dir, a.force)
    late = []
    for i, act in enumerate(acts):
        length = sf.info(wavs[act["id"]]).duration
        end = act.get("end", acts[i + 1]["start"] if i + 1 < len(acts) else cfg["duration"])
        room = end - act["start"]
        flag = "" if length <= room - 0.3 else "  << runs past the act"
        if flag:
            late.append(act["id"])
        print(f"  {act['id']}: {length:5.2f}s spoken, starts {act['start']:5.2f}s, room {room:5.2f}s{flag}")

    inputs, chains, labels = [], [], []
    if cfg.get("music"):
        bg = audio_dir / "music.wav"
        music(acts, cfg["duration"], bg)
        inputs += ["-i", str(bg)]
        chains.append(f"[0:a]volume={cfg['music']['volume']}[bg]")
        labels.append("[bg]")
    base = len(inputs) // 2
    for i, act in enumerate(acts):
        inputs += ["-i", str(wavs[act["id"]])]
        ms = int(round(act["start"] * 1000))
        chains.append(f"[{base + i}:a]adelay={ms}|{ms},volume={cfg['voiceVolume']}[a{i}]")
        labels.append(f"[a{i}]")
    fade = cfg["duration"] - 1.5
    graph = ";".join(chains) + ";" + "".join(labels) + \
        f"amix=inputs={len(labels)}:duration=longest:dropout_transition=2,apad,afade=t=out:st={fade}:d=1.5[out]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", graph, "-map", "[out]",
                    "-t", str(cfg["duration"]), str(master)], check=True)
    print(f"[audio] {master} ({cfg['duration']}s)")
    if late:
        print(f"[audio] FAIL: {', '.join(late)} run past their act; shorten the text", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
