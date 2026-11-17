#!/usr/bin/env python3
"""Measure agent response latency from the separated call recordings.

Finds pairs <base>-caller.wav[16] / <base>-agent.wav[16] in a directory (recursive),
runs a frame-energy voice activity detector on each track and computes, for
every caller turn followed by agent speech within 10 s:

    latency = agent speech onset - preceding caller speech offset

It also counts barge-in overlaps (the caller starts talking while the agent is
talking). Prints per-call stats (turns, median, p95, max) and an aggregate per
provider (provider = first token of the base name, e.g. "openai-turno-...").

This is "mouth-to-ear on the PBX side": it measures what the Asterisk
emulator sees and excludes the Rosario -> US leg, which the T100 window
measures.

Input: 16-bit mono PCM WAV at 8 kHz or 16 kHz. Standard library only.
"""

import argparse
import csv
import math
import statistics
import sys
import wave
from array import array
from pathlib import Path

FRAME_MS = 20
MAX_RESPONSE_S = 10.0


def read_wav(path):
    """Return (samples, rate) for a 16-bit mono 8/16 kHz WAV, else raise ValueError."""
    with wave.open(str(path), "rb") as wf:
        channels, width, rate = wf.getnchannels(), wf.getsampwidth(), wf.getframerate()
        if channels != 1 or width != 2 or rate not in (8000, 16000):
            raise ValueError(
                f"{path.name}: unsupported format ({channels} ch, {width * 8}-bit, {rate} Hz); "
                "expected 16-bit mono at 8000 or 16000 Hz"
            )
        raw = wf.readframes(wf.getnframes())
    samples = array("h")
    samples.frombytes(raw)
    if sys.byteorder == "big":
        samples.byteswap()
    return samples, rate


def frame_rms(samples, rate):
    n = rate * FRAME_MS // 1000
    out = []
    for i in range(0, len(samples) - n + 1, n):
        chunk = samples[i : i + n]
        out.append(math.sqrt(sum(s * s for s in chunk) / n))
    return out


def detect_segments(samples, rate, noise_factor, min_rms, min_speech_ms, min_silence_ms):
    """Return a list of (start_s, end_s) speech segments."""
    rms = frame_rms(samples, rate)
    if not rms:
        return []
    ordered = sorted(rms)
    floor = ordered[int(len(ordered) * 0.10)]
    threshold = max(floor * noise_factor, min_rms)
    active = [r > threshold for r in rms]

    # Runs of active frames.
    runs = []
    start = None
    for i, a in enumerate(active):
        if a and start is None:
            start = i
        elif not a and start is not None:
            runs.append([start, i])
            start = None
    if start is not None:
        runs.append([start, len(active)])

    # Merge runs separated by less than min_silence (hangover).
    gap = max(1, min_silence_ms // FRAME_MS)
    merged = []
    for run in runs:
        if merged and run[0] - merged[-1][1] < gap:
            merged[-1][1] = run[1]
        else:
            merged.append(run)

    min_frames = max(1, min_speech_ms // FRAME_MS)
    frame_s = FRAME_MS / 1000.0
    return [(a * frame_s, b * frame_s) for a, b in merged if b - a >= min_frames]


def analyze(caller, agent):
    """Return (latencies list of dicts, barge_in_count)."""
    turns = []
    overlaps = 0
    for i, (c_start, c_end) in enumerate(caller):
        if any(a_start < c_start < a_end for a_start, a_end in agent):
            overlaps += 1
        if any(a_start <= c_end < a_end for a_start, a_end in agent):
            continue  # agent was already talking at caller offset: not a response
        next_caller = caller[i + 1][0] if i + 1 < len(caller) else math.inf
        for a_start, _ in agent:
            if a_start < c_end:
                continue
            if a_start - c_end <= MAX_RESPONSE_S and a_start < next_caller:
                turns.append(
                    {
                        "turn": i + 1,
                        "caller_end_s": c_end,
                        "agent_start_s": a_start,
                        "latency_ms": (a_start - c_end) * 1000.0,
                    }
                )
            break
    return turns, overlaps


def percentile(values, pct):
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * pct / 100.0
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def summarize(values):
    if not values:
        return None
    return {
        "median": statistics.median(values),
        "p95": percentile(values, 95),
        "max": max(values),
    }


def fmt(stats):
    if stats is None:
        return "median -    p95 -    max -"
    return f"median {stats['median']:.0f} ms  p95 {stats['p95']:.0f} ms  max {stats['max']:.0f} ms"


def main():
    parser = argparse.ArgumentParser(description="Agent response latency from caller/agent tracks.")
    parser.add_argument("directory", nargs="?", default="recordings", help="recordings directory (default: recordings)")
    parser.add_argument("--csv", metavar="FILE", help="write one row per measured turn")
    parser.add_argument("--noise-factor", type=float, default=4.0, help="threshold = noise floor x factor (default 4)")
    parser.add_argument("--min-rms", type=float, default=100.0, help="absolute RMS floor for the threshold (default 100)")
    parser.add_argument("--min-speech-ms", type=int, default=200, help="minimum speech segment (default 200)")
    parser.add_argument("--min-silence-ms", type=int, default=300, help="silence needed to split segments (default 300)")
    args = parser.parse_args()

    root = Path(args.directory)
    if not root.is_dir():
        sys.exit(f"error: {root} is not a directory")
    # Asterisk writes 16 kHz WAV as ".wav16"; older recordings are ".wav".
    pairs = []
    for ext in (".wav", ".wav16"):
        for c in sorted(root.rglob(f"*-caller{ext}")):
            a = c.with_name(c.name[: -len(f"-caller{ext}")] + f"-agent{ext}")
            if a.is_file():
                pairs.append((c, a))
    if not pairs:
        sys.exit(f"error: no <base>-caller.wav[16] / <base>-agent.wav[16] pairs found in {root}")

    rows = []
    per_provider = {}
    for caller_path, agent_path in pairs:
        base = caller_path.name.rsplit("-caller.", 1)[0]
        parts = base.split("-")
        provider = parts[0]
        flow = parts[1] if len(parts) > 1 else ""
        try:
            c_samples, c_rate = read_wav(caller_path)
            a_samples, a_rate = read_wav(agent_path)
        except (ValueError, wave.Error, EOFError) as exc:
            sys.exit(f"error: {exc}")
        opts = (args.noise_factor, args.min_rms, args.min_speech_ms, args.min_silence_ms)
        caller = detect_segments(c_samples, c_rate, *opts)
        agent = detect_segments(a_samples, a_rate, *opts)
        turns, overlaps = analyze(caller, agent)
        lats = [t["latency_ms"] for t in turns]
        print(f"{base}: turns={len(turns)} barge_in_overlaps={overlaps}  {fmt(summarize(lats))}")
        bucket = per_provider.setdefault(provider, {"calls": 0, "lats": [], "overlaps": 0})
        bucket["calls"] += 1
        bucket["lats"].extend(lats)
        bucket["overlaps"] += overlaps
        for t in turns:
            rows.append(
                {
                    "base": base,
                    "provider": provider,
                    "flow": flow,
                    "turn": t["turn"],
                    "caller_end_s": round(t["caller_end_s"], 3),
                    "agent_start_s": round(t["agent_start_s"], 3),
                    "latency_ms": round(t["latency_ms"], 1),
                }
            )

    print("\nAggregate per provider")
    for provider in sorted(per_provider):
        b = per_provider[provider]
        print(f"  {provider}: calls={b['calls']} turns={len(b['lats'])} barge_in_overlaps={b['overlaps']}  {fmt(summarize(b['lats']))}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["base", "provider", "flow", "turn", "caller_end_s", "agent_start_s", "latency_ms"]
            )
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nCSV written to {args.csv}")


if __name__ == "__main__":
    main()
