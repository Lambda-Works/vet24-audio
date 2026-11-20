#!/usr/bin/env bash
# ElevenLabs agent and SIP number as code, through the official CLI pinned to
# one version. Agent configs live in elevenlabs/ (agents.json + agent_configs/),
# the SIP number config in elevenlabs/phone_number.json.
#
# Auth: `scripts/elevenlabs.sh auth login`, or ELEVENLABS_API_KEY in
# elevenlabs/.env (gitignored). Never commit a key.
set -euo pipefail

CLI_VERSION="1.9.0"   # newest release >= 2 weeks old when pinned (2026-11-20)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="$ROOT/elevenlabs"
PHONE_FILE="$DIR/phone_number.json"

cli() { (cd "$DIR" && npx -y "@elevenlabs/cli@${CLI_VERSION}" "$@"); }

phone_id() {
  python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["phone_number_id"])' "$PHONE_FILE"
}

# Body for PATCH /v1/convai/phone-numbers/{id}: every key except the id.
phone_body() {
  python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); d.pop("phone_number_id"); print(json.dumps(d))' "$PHONE_FILE"
}

usage() {
  cat <<'EOF'
Usage: scripts/elevenlabs.sh <command> [args]

  auth <login|status|logout>   manage CLI credentials
  pull --agent <id>            download an agent config into elevenlabs/
  status                       show local vs remote agent state
  push [--dry-run]             upload local agent configs
  phone-show                   print the SIP number config from ElevenLabs
  phone-apply                  apply elevenlabs/phone_number.json to ElevenLabs
  cli <args...>                run any CLI command (pinned version)
EOF
}

cmd=${1:-help}
shift || true
case "$cmd" in
  auth)        cli auth "$@" ;;
  pull)        cli agents pull "$@" ;;
  status)      cli agents status "$@" ;;
  push)        cli agents push "$@" ;;
  phone-show)  cli agents phone-numbers get --phone-number-id "$(phone_id)" --format json ;;
  phone-apply) phone_body | cli agents phone-numbers update --phone-number-id "$(phone_id)" --json - --format json ;;
  cli)         cli "$@" ;;
  help|-h|--help) usage ;;
  *) echo "unknown command: $cmd" >&2; usage >&2; exit 1 ;;
esac
