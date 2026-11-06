#!/usr/bin/env bash
# Renders the Asterisk configuration from templates + environment, prepares
# TLS certificates, holidays and prompt symlinks, then starts Asterisk.
set -euo pipefail

CONF_SRC=/opt/lab/config
CONF_DST=/etc/asterisk
KEYS_DIR=/etc/asterisk/keys
LAB_TZ=America/Argentina/Cordoba

log()  { echo "[entrypoint] $*"; }
warn() { echo "[entrypoint] WARNING: $*" >&2; }
die()  { echo "[entrypoint] ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------- validation
missing=()
for v in PUBLIC_IP SOFTPHONE_PASSWORD LAB_CALLER_ID VOICEMAIL_PIN; do
  [[ -n "${!v:-}" ]] || missing+=("$v")
done
if ((${#missing[@]} > 0)); then
  die "required variables not set in .env: ${missing[*]}"
fi

# ------------------------------------------------------------------ defaults
# envsubst has no ${VAR:-default}, so defaults are resolved here and exported.
export LAB_FQDN="${LAB_FQDN:-$PUBLIC_IP}"
export SOFTPHONE_USER="${SOFTPHONE_USER:-1001}"
export TIME_MODE="${TIME_MODE:-auto}"
export OFFICE_HOURS="${OFFICE_HOURS:-09:00-20:59}"
export NIGHT_PROVIDER="${NIGHT_PROVIDER:-openai}"
export PROVIDER_ANSWER_TIMEOUT="${PROVIDER_ANSWER_TIMEOUT:-20}"
export AGENT_TURN_TIMEOUT="${AGENT_TURN_TIMEOUT:-20}"
export BARGE_DELAY="${BARGE_DELAY:-2}"
export RTP_START="${RTP_START:-10000}"
export RTP_END="${RTP_END:-10199}"
export ELEVENLABS_MEDIA_ENCRYPTION="${ELEVENLABS_MEDIA_ENCRYPTION:-sdes}"
export LIVEKIT_MEDIA_ENCRYPTION="${LIVEKIT_MEDIA_ENCRYPTION:-sdes}"

case "$TIME_MODE" in auto|night|day) ;; *) die "TIME_MODE must be auto, night or day (got '$TIME_MODE')";; esac
case "$NIGHT_PROVIDER" in openai|elevenlabs|livekit) ;; *) die "NIGHT_PROVIDER must be openai, elevenlabs or livekit (got '$NIGHT_PROVIDER')";; esac
for v in ELEVENLABS_MEDIA_ENCRYPTION LIVEKIT_MEDIA_ENCRYPTION; do
  case "${!v}" in sdes|no) ;; *) die "$v must be sdes or no (got '${!v}')";; esac
done

# ------------------------------------------------------------------ TLS certs
mkdir -p "$KEYS_DIR"
if [[ -f /lab/certs/fullchain.pem && -f /lab/certs/privkey.pem ]]; then
  log "using certificate from /lab/certs/fullchain.pem"
  src_cert=/lab/certs/fullchain.pem
  src_key=/lab/certs/privkey.pem
else
  src_cert=/lab/certs/selfsigned-cert.pem
  src_key=/lab/certs/selfsigned-key.pem
  if [[ ! -f $src_cert || ! -f $src_key ]]; then
    log "generating self-signed certificate for ${LAB_FQDN}"
    if [[ $LAB_FQDN =~ ^[0-9.]+$ ]]; then san="IP:${LAB_FQDN}"; else san="DNS:${LAB_FQDN}"; fi
    openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
      -subj "/CN=${LAB_FQDN}" -addext "subjectAltName=${san}" \
      -keyout "$src_key" -out "$src_cert" 2>/dev/null
  fi
  warn "using a SELF-SIGNED certificate. Outbound calls work, but ElevenLabs follow-up requests (BYE/REFER over a new TLS connection) need a trusted certificate for ${LAB_FQDN}. Put fullchain.pem and privkey.pem in certs/ (e.g. Let's Encrypt)."
fi
# Copy so the unprivileged asterisk user can read the key regardless of host permissions.
install -o asterisk -g asterisk -m 0644 "$src_cert" "$KEYS_DIR/cert.pem"
install -o asterisk -g asterisk -m 0600 "$src_key"  "$KEYS_DIR/key.pem"
export TLS_CERT_FILE="$KEYS_DIR/cert.pem"
export TLS_KEY_FILE="$KEYS_DIR/key.pem"

# ------------------------------------------------------ render configuration
# Explicit list: dialplan variables such as ${EXTEN} must stay untouched.
# ";" would start a comment in the rendered .conf files: escape it in secrets.
SOFTPHONE_PASSWORD="${SOFTPHONE_PASSWORD//;/\\;}"
VOICEMAIL_PIN="${VOICEMAIL_PIN//;/\\;}"
export SOFTPHONE_PASSWORD VOICEMAIL_PIN

SUBST_VARS='${PUBLIC_IP} ${LAB_FQDN} ${SOFTPHONE_USER} ${SOFTPHONE_PASSWORD} ${VOICEMAIL_PIN} ${RTP_START} ${RTP_END} ${TLS_CERT_FILE} ${TLS_KEY_FILE}'

for f in "$CONF_SRC"/*; do
  name=$(basename "$f")
  if [[ $name == *.tmpl ]]; then
    envsubst "$SUBST_VARS" < "$f" > "$CONF_DST/${name%.tmpl}"
  else
    cp "$f" "$CONF_DST/$name"
  fi
done

# ------------------------------------------- provider-specific PJSIP sections
PJ="$CONF_DST/pjsip.conf"

# emit_provider <name> <host> <encryption> <optimistic> <auth_user> <auth_pass>
emit_provider() {
  local name=$1 host=$2 enc=$3 optimistic=$4 auth_user=$5 auth_pass=$6
  {
    echo
    echo "; ---- provider: ${name} ----"
    echo "[${name}]"
    echo "type=aor"
    # ";" starts a comment in Asterisk .conf files: it must be escaped.
    echo "contact=sip:${host}:5061\;transport=tls"
    echo
    if [[ -n $auth_user ]]; then
      echo "[${name}-auth]"
      echo "type=auth"
      echo "auth_type=userpass"
      echo "username=${auth_user//;/\\;}"
      echo "password=${auth_pass//;/\\;}"
      echo
    fi
    echo "[${name}]"
    echo "type=endpoint"
    echo "transport=transport-tls"
    echo "aors=${name}"
    [[ -n $auth_user ]] && echo "outbound_auth=${name}-auth"
    echo "context=from-provider"
    echo "disallow=all"
    echo "allow=g722,ulaw,alaw"
    echo "language=es"
    echo "direct_media=no"
    echo "rtp_symmetric=yes"
    echo "force_rport=yes"
    echo "rewrite_contact=yes"
    echo "send_pai=yes"
    echo "trust_id_outbound=yes"
    echo "allow_transfer=yes"
    echo "dtmf_mode=rfc4733"
    echo "from_domain=${LAB_FQDN}"
    # Out-of-dialog INVITEs must not match a provider endpoint by From user.
    echo "identify_by=auth_username"
    if [[ $enc == sdes ]]; then
      echo "media_encryption=sdes"
      echo "media_encryption_optimistic=${optimistic}"
    else
      echo "media_encryption=no"
    fi
  } >> "$PJ"
}

{
  echo
  echo "; ======== generated by entrypoint.sh: provider sections ========"
  echo "; No identify sections: provider requests (REFER, BYE) arrive in-dialog."
  echo "; identify_by=auth_username keeps stray out-of-dialog INVITEs from matching a provider."
} >> "$PJ"

enabled=()
if [[ -n ${OPENAI_PROJECT_ID:-} ]]; then
  emit_provider openai sip.api.openai.com sdes no "" ""
  enabled+=(openai)
fi
if [[ -n ${ELEVENLABS_NUMBER:-} ]]; then
  emit_provider elevenlabs sip.rtc.elevenlabs.io "$ELEVENLABS_MEDIA_ENCRYPTION" yes \
    "${ELEVENLABS_SIP_USER:-}" "${ELEVENLABS_SIP_PASSWORD:-}"
  enabled+=(elevenlabs)
fi
if [[ -n ${LIVEKIT_SIP_HOST:-} ]]; then
  emit_provider livekit "$LIVEKIT_SIP_HOST" "$LIVEKIT_MEDIA_ENCRYPTION" yes \
    "${LIVEKIT_SIP_USER:-}" "${LIVEKIT_SIP_PASSWORD:-}"
  enabled+=(livekit)
fi
if ((${#enabled[@]} == 0)); then
  warn "no provider configured (OPENAI_PROJECT_ID, ELEVENLABS_NUMBER, LIVEKIT_SIP_HOST all empty)"
else
  log "providers enabled: ${enabled[*]}"
fi

# ------------------------------------------------------------------ holidays
HOL_OUT="$CONF_DST/extensions_feriados.conf"
{
  echo "; generated by entrypoint.sh from /lab/feriados.txt - do not edit"
  echo "[sub-check-holiday]"
  echo "; Sets HOLIDAY=1 when today (in ${LAB_TZ}) is listed, else HOLIDAY=0."
  echo "exten => s,1,Set(HOLIDAY=0)"
  echo " same => n,Set(TODAY=\${STRFTIME(\${EPOCH},${LAB_TZ},%Y-%m-%d)})"
} > "$HOL_OUT"

hol_dates=()
if [[ -f /lab/feriados.txt ]]; then
  while IFS= read -r line || [[ -n $line ]]; do
    line=${line%%#*}
    line=${line//[[:space:]]/}
    [[ -z $line ]] && continue
    if [[ $line =~ ^([0-9]{4})-([0-9]{2})-([0-9]{2})$ ]]; then
      y=${BASH_REMATCH[1]}; m=$((10#${BASH_REMATCH[2]})); d=$((10#${BASH_REMATCH[3]}))
      if ((m < 1 || m > 12 || d < 1 || d > 31)); then
        warn "invalid date ignored in feriados.txt: $line"; continue
      fi
      hol_dates+=("$line")
    else
      warn "line ignored in feriados.txt (expected YYYY-MM-DD): $line"
    fi
  done < /lab/feriados.txt
else
  warn "/lab/feriados.txt not found: no holidays loaded"
fi

# Compare today's full date (in LAB_TZ) against each listed YYYY-MM-DD.
for entry in "${hol_dates[@]}"; do
  echo " same => n,ExecIf(\$[\"\${TODAY}\"=\"${entry}\"]?Set(HOLIDAY=1))" >> "$HOL_OUT"
done
echo " same => n,Return()" >> "$HOL_OUT"
log "holidays loaded: ${#hol_dates[@]}"

# --------------------------------------------------------- prompts + sounds
# Dialplan plays lab/<flow>/<NN>; on Ubuntu noble the data dir is
# /usr/share/asterisk/sounds. Always link there; link /var/lib too if it exists.
mkdir -p /lab/prompts/asterisk /usr/share/asterisk/sounds
ln -sfn /lab/prompts/asterisk /usr/share/asterisk/sounds/lab
if [[ -d /var/lib/asterisk/sounds ]]; then
  ln -sfn /lab/prompts/asterisk /var/lib/asterisk/sounds/lab
fi

# ---------------------------------------------------------------- ownership
mkdir -p /var/spool/asterisk/monitor /var/spool/asterisk/voicemail \
         /var/log/asterisk /var/run/asterisk
chown -R asterisk:asterisk /var/spool/asterisk/monitor /var/spool/asterisk/voicemail \
      /var/log/asterisk /var/run/asterisk "$CONF_DST" 2>/dev/null || true
chmod 0775 /var/spool/asterisk/monitor

log "starting Asterisk (TIME_MODE=${TIME_MODE}, NIGHT_PROVIDER=${NIGHT_PROVIDER})"
exec asterisk -f -U asterisk -G asterisk -vvv -g
