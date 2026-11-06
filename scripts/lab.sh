#!/usr/bin/env bash
# Helper for the Vet24 SIP lab. Run from anywhere; commands are executed from the repo root.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROVIDERS=(openai elevenlabs livekit)
SUITE_SLEEP=3        # seconds between calls in a suite
SUITE_TIMEOUT=180    # max seconds to wait for a call to finish

usage() {
  cat <<'EOF'
Usage: scripts/lab.sh <command> [args]

  up                       docker compose up -d --build
  down                     docker compose down
  logs                     follow Asterisk logs
  cli                      open the Asterisk CLI (asterisk -rvvv)
  call <provider> <flow>   place one scripted test call
  suite <provider> [flow..] run flows one at a time (all flows by default)
  prompts                  generate caller voices (OpenAI TTS) and convert to .sln16
  latency [recordings_dir] measure agent latency from recordings
  help                     show this help

Providers: openai | elevenlabs | livekit
Flows: names of tests/flows/*.txt (letters only)
EOF
}

dc() { docker compose "$@"; }
ast() { dc exec -T asterisk asterisk -rx "$1"; }

valid_provider() {
  local p
  for p in "${PROVIDERS[@]}"; do [[ $p == "$1" ]] && return 0; done
  return 1
}

all_flows() {
  local f
  for f in tests/flows/*.txt; do
    [[ -e $f ]] || continue
    basename "$f" .txt
  done
}

check_flow() {
  local flow=$1
  [[ $flow =~ ^[a-z]+$ ]] || { echo "error: invalid flow name '$flow' (letters a-z only)" >&2; return 1; }
  [[ -f tests/flows/$flow.txt ]] || { echo "error: tests/flows/$flow.txt does not exist" >&2; return 1; }
  [[ -f prompts/asterisk/$flow/01.sln16 ]] || {
    echo "error: prompts for '$flow' not found in prompts/asterisk/$flow. Run: scripts/lab.sh prompts" >&2
    return 1
  }
}

cmd_call() {
  local provider=${1:-} flow=${2:-}
  [[ -n $provider && -n $flow ]] || { echo "usage: lab.sh call <provider> <flow>" >&2; return 1; }
  valid_provider "$provider" || { echo "error: unknown provider '$provider' (${PROVIDERS[*]})" >&2; return 1; }
  check_flow "$flow"
  echo "Calling $provider with flow $flow ..."
  ast "channel originate Local/${provider}-${flow}@lab-run/n extension ${flow}@lab-script"
}

active_calls() {
  local out
  out=$(ast "core show channels count" 2>/dev/null || true)
  if [[ $out =~ ([0-9]+)\ active\ channel ]]; then
    echo "${BASH_REMATCH[1]}"
  else
    echo "-1"
  fi
}

wait_idle() {
  local waited=0 n
  sleep 3
  while ((waited < SUITE_TIMEOUT)); do
    n=$(active_calls)
    if [[ $n == 0 ]]; then return 0; fi
    sleep 2
    waited=$((waited + 2))
  done
  echo "warning: timeout waiting for calls to finish; hanging up" >&2
  ast "channel request hangup all" >/dev/null || true
  return 1
}

cmd_suite() {
  local provider=${1:-}
  [[ -n $provider ]] || { echo "usage: lab.sh suite <provider> [flow...]" >&2; return 1; }
  shift
  valid_provider "$provider" || { echo "error: unknown provider '$provider' (${PROVIDERS[*]})" >&2; return 1; }
  local flows=("$@")
  if ((${#flows[@]} == 0)); then
    mapfile -t flows < <(all_flows)
  fi
  local flow
  for flow in "${flows[@]}"; do check_flow "$flow"; done
  for flow in "${flows[@]}"; do
    echo "=== $provider / $flow ==="
    cmd_call "$provider" "$flow"
    wait_idle || true
    sleep "$SUITE_SLEEP"
  done
  echo "Suite finished. Measure with: scripts/lab.sh latency"
}

cmd_prompts() {
  python3 scripts/generate_prompts.py "$@"
  [[ -d prompts/raw ]] || { echo "error: prompts/raw does not exist" >&2; return 1; }
  echo "Converting to 16 kHz mono signed-linear (.sln16) inside the container ..."
  dc exec -T asterisk bash -s <<'EOF'
set -euo pipefail
RAW=/lab/prompts/raw
OUT=/lab/prompts/asterisk
mkdir -p "$OUT"
shopt -s nullglob
for wav in "$RAW"/*/*.wav; do
  flow=$(basename "$(dirname "$wav")")
  nn=$(basename "$wav" .wav)
  mkdir -p "$OUT/$flow"
  dst="$OUT/$flow/$nn.sln16"
  if [[ $flow == ruido ]]; then
    # Mix low-volume brown noise (same rate and duration as the utterance).
    rate=$(soxi -r "$wav")
    dur=$(soxi -D "$wav")
    sox -m -v 1.0 "$wav" -v 1.0 "|sox -n -r $rate -c 1 -b 16 -t wav - synth $dur brownnoise vol 0.08" \
      -r 16000 -c 1 -b 16 -e signed-integer -t raw "$dst"
  else
    sox "$wav" -r 16000 -c 1 -b 16 -e signed-integer -t raw "$dst"
  fi
  if [[ -f "$RAW/$flow/$nn.barge" ]]; then
    cp "$RAW/$flow/$nn.barge" "$OUT/$flow/$nn.barge"
  else
    rm -f "$OUT/$flow/$nn.barge"
  fi
  chmod 0644 "$dst"
done
# Remove converted files whose raw wav no longer exists.
for out in "$OUT"/*/*.sln16 "$OUT"/*/*.barge; do
  flow=$(basename "$(dirname "$out")")
  nn=$(basename "${out%.*}")
  if [[ ! -f "$RAW/$flow/$nn.wav" ]]; then
    rm -f "$out"
    echo "removed orphan $flow/$(basename "$out")"
  fi
done
echo "done"
EOF
}

cmd_latency() {
  python3 scripts/measure_latency.py "${1:-recordings}"
}

main() {
  local cmd=${1:-help}
  shift || true
  case "$cmd" in
    up)       [[ -f .env ]] || { echo "error: .env not found (copy .env.example)" >&2; exit 1; }
              dc up -d --build ;;
    down)     dc down ;;
    logs)     dc logs -f --tail=200 asterisk ;;
    cli)      dc exec asterisk asterisk -rvvv ;;
    call)     cmd_call "$@" ;;
    suite)    cmd_suite "$@" ;;
    prompts)  cmd_prompts "$@" ;;
    latency)  cmd_latency "$@" ;;
    help|-h|--help) usage ;;
    *)        echo "error: unknown command '$cmd'" >&2; usage >&2; exit 1 ;;
  esac
}

main "$@"
