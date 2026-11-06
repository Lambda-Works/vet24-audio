#!/usr/bin/env python3
"""Generate caller voice prompts for the scripted test calls.

Reads tests/flows/*.txt. In each file:
  - lines starting with '#' are comments ('# espera:' describes the expected
    agent behavior and is not spoken);
  - every other non-empty line is a caller utterance;
  - a leading '>' marks a barge-in utterance (the marker is stripped and an
    empty NN.barge file is written next to the audio).

Each utterance is synthesized with the OpenAI speech endpoint and written to
prompts/raw/<flow>/NN.wav (NN = zero-padded 2 digits) and the utterance to
NN.txt. A wav is regenerated when it or its NN.txt is missing, when the text
changed, or with --force. NN.* files beyond the current utterance count of a
flow are deleted. --dry-run only prints what would happen (no network, no
writes). Conversion to Asterisk format is done by `scripts/lab.sh prompts`.

Environment (or .env.tts on the host, never read by the container):
OPENAI_API_KEY (required), TTS_MODEL, TTS_VOICE.
Standard library only.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
API_URL = "https://api.openai.com/v1/audio/speech"
DEFAULT_MODEL = "gpt-4o-mini-tts"
DEFAULT_VOICE = "coral"
INSTRUCTIONS = (
    "Habla en español rioplatense natural, como una persona que llama por teléfono "
    "a una clínica veterinaria de noche en Rosario: tono cotidiano, espontáneo, "
    "ritmo normal, sin sonar a locutor ni exagerar."
)


def load_dotenv(path):
    """Tiny .env parser: KEY=VALUE lines, optional quotes, '#' comments."""
    values = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        values[key.strip()] = val
    return values


def parse_flow(path):
    """Return a list of (text, is_barge) for a flow file."""
    items = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        barge = line.startswith(">")
        if barge:
            line = line[1:].strip()
        if line:
            items.append((line, barge))
    return items


def synthesize(api_key, model, voice, text):
    body = json.dumps(
        {
            "model": model,
            "voice": voice,
            "input": text,
            "instructions": INSTRUCTIONS,
            "response_format": "wav",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"OpenAI API returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"could not reach the OpenAI API: {exc.reason}") from exc


def sync_flow(flow, items, out_dir, force, dry_run, generate):
    """Bring out_dir in line with items. Returns (generated, skipped, deleted)."""
    generated = skipped = deleted = 0
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
    for idx, (text, barge) in enumerate(items, start=1):
        nn = f"{idx:02d}"
        wav, txt, marker = (out_dir / f"{nn}.{ext}" for ext in ("wav", "txt", "barge"))
        if barge and not marker.exists():
            if not dry_run:
                marker.touch()
        elif not barge and marker.exists():
            if not dry_run:
                marker.unlink()
        stale = force or not wav.exists() or not txt.exists() or txt.read_text(encoding="utf-8") != text
        if not stale:
            skipped += 1
            continue
        print(f"[{flow}/{nn}] {'would generate' if dry_run else 'generating'}: {text}")
        if not dry_run:
            wav.write_bytes(generate(text))
            txt.write_text(text, encoding="utf-8")  # after the wav: a failure retriggers
        generated += 1
    # Orphans: NN.* with NN greater than the current utterance count.
    if out_dir.is_dir():
        for path in sorted(out_dir.iterdir()):
            stem = path.name.split(".", 1)[0]
            if stem.isdigit() and int(stem) > len(items):
                print(f"[{flow}] {'would delete' if dry_run else 'deleting'} orphan {path.name}")
                if not dry_run:
                    path.unlink()
                deleted += 1
    return generated, skipped, deleted


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--flow", nargs="+", metavar="NAME", help="only these flows")
    parser.add_argument("--force", action="store_true", help="regenerate existing files")
    parser.add_argument("--dry-run", action="store_true", help="print actions only; no network, no writes")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args()

    root = args.root
    flows_dir = root / "tests" / "flows"
    raw_dir = root / "prompts" / "raw"
    dotenv = load_dotenv(root / ".env.tts")

    def setting(name, default=""):
        return os.environ.get(name) or dotenv.get(name) or default

    api_key = setting("OPENAI_API_KEY")
    if not api_key and not args.dry_run:
        sys.exit("error: OPENAI_API_KEY is not set (environment or .env.tts)")
    model = setting("TTS_MODEL", DEFAULT_MODEL)
    voice = setting("TTS_VOICE", DEFAULT_VOICE)

    flow_files = sorted(flows_dir.glob("*.txt"))
    if not flow_files:
        sys.exit(f"error: no flow files found in {flows_dir}")
    if args.flow:
        known = {p.stem for p in flow_files}
        unknown = [f for f in args.flow if f not in known]
        if unknown:
            sys.exit(f"error: unknown flow(s): {', '.join(unknown)} (known: {', '.join(sorted(known))})")
        flow_files = [p for p in flow_files if p.stem in args.flow]

    def generate(text):
        try:
            return synthesize(api_key, model, voice, text)
        except RuntimeError as exc:
            sys.exit(f"error: {exc}")

    totals = [0, 0, 0]
    for flow_file in flow_files:
        res = sync_flow(flow_file.stem, parse_flow(flow_file), raw_dir / flow_file.stem, args.force, args.dry_run, generate)
        totals = [a + b for a, b in zip(totals, res)]
    prefix = "dry-run: " if args.dry_run else ""
    print(f"{prefix}done: {totals[0]} generated, {totals[1]} up to date, {totals[2]} orphans removed (model={model}, voice={voice})")


if __name__ == "__main__":
    main()
