# vet24-audio (SIP lab)

Lab for **Vet24**, a veterinary clinic in Rosario, Argentina. Hub project `Vet24`, id `ba39bd9b-052c-41c0-9274-14dba144d089`. Between 21:00 and 09:00 and on holidays, the clinic's ZYCOO **CooVox-T100** PBX sends calls by SIP directly (no Twilio) to an AI voice agent. This repo emulates the T100 with Asterisk so providers can be tested before touching the real PBX.

- **Plan (source of truth for scope, decisions, timeline):** [Vet24 · Plan del asistente fuera de horario](https://claude.ai/artifact/Tun2eGWMZvvg4CBmNFg28t). Read it with the Claude Docs tools, never by web fetch.
- Repo `Lambda-Works/vet24` was only the 48 h sales prototype. Ignore it.
- Run the Hub's `get_context` with this repo's remote at session start. Project memories and decisions live there.

## Decisions (do not re-litigate)

| Date | Decision |
| --- | --- |
| 2026-11-20 | **Voice provider: ElevenLabs Agents.** Lab median latency 1070 ms vs 1940–2060 ms for OpenAI Realtime, and a more natural voice. |
| 2026-11-06 | Provider accounts belong to LambdaWorks, with a low spend limit. |
| 2026-11-06 | The lab runs by hand on the shared Hub VPS, outside the Hub (see Operations). The user chose this knowing it breaks the "never deploy by hand" rule. |
| 2026-11-19 | The OpenAI webhook (`webhook/`) is deployed by the Hub to Vet24 development, replacing the prototype. It stays as a reference only; don't extend it unless asked. |

## Layout

| Path | What it is |
| --- | --- |
| `docker-compose.yml`, `asterisk/` | Asterisk 20 "T100" (runs by hand, `network_mode: host`). `entrypoint.sh` renders `*.tmpl` from `.env`; a provider is enabled only when its vars are set. |
| `asterisk/config/extensions.conf` | Dialplan. `1` = OpenAI, `2` = ElevenLabs, `3` = LiveKit, `100` = clinic number with time rule, `600` = echo, `*98` = voicemail. REFER lands in `[from-provider]` `urgencias`. |
| `scripts/lab.sh` | `up`, `logs`, `cli`, `call`, `suite`, `prompts`, `latency` |
| `scripts/measure_latency.py` | Latency from separated tracks (`*-agent.wav16` / `*-caller.wav16`) |
| `tests/flows/*.txt` | The 12 scripted flows = the functional scope agreed with the client; each `# espera` line is the expected outcome |
| `webhook/`, `docker-compose.prod.yml` | OpenAI Realtime SIP webhook (FastAPI). The Hub only runs `docker-compose.prod.yml` (single `backend` service). |

## Operations

- **VPS:** 72.61.50.55 (Hostinger, São Paulo). This is the shared Hub server. User `lambdaworks`, **no sudo**, no Hestia admin panel. The lab lives in `~/vet24-sip-lab`; update it with `git pull && scripts/lab.sh up`. Remote work needs the user's explicit authorization; normally the user runs the commands and pastes output.
- **Firewall, DNS, certificates** are handled by a server admin: 5061/tcp and 10000-10199/udp are open, and 5060/udp is open only for one fixed IP. `sip-lab.lambdaworks.ar` has a Let's Encrypt cert (expires 2027-02-15). The files in `certs/` are copies: recopy them and restart on renewal.
- **Softphone:** Linphone, user `1001`, registers over **TLS to `sip-lab.lambdaworks.ar:5061`** (the user's home IP is dynamic).
- **Webhook deploys:** through Hub MCP tools on Vet24 `development` from branch `develop`. Keep `develop` equal to `main`. Live at `https://dev.vet24.api.lambdaworks.ar/openai/webhook`. Secrets (`OPENAI_API_KEY`, `OPENAI_WEBHOOK_SECRET`) are loaded by the user in the Hub UI, never through chat.

## Gotchas already paid for

- `;` starts a comment in Asterisk `.conf`: escape it as `\;` in rendered values.
- `res_resolver_unbound` chokes on Hestia's `/etc/hosts`. Every lookup fails and calls end in `CONGESTION`. It is `noload` in `modules.conf`.
- pjproject rejects OpenAI's wildcard cert (`*.api.openai.com`). `verify_server=no` on `transport-tls`, a lab-only compromise.
- Recordings are `.wav16`. Wideband needs G.722 on both legs. The real PSTN caller arrives as G.711.
- Manual-call latency is noisy without headphones (echo inflates barge-in overlaps). Use the scripted suite for comparable numbers.

## Next tracks

- **T100 window with Faxtel:** steps and questions are in the plan, section "Ventana con la T100".
- **WhatsApp after-hours bot:** must cover the same functionality as the night call (`tests/flows`). All clinic data comes from **Mercurio's APIs**; LambdaWorks doesn't own Vet24's system. Use deterministic buttons for flows and a cheap LLM (DeepSeek-like) only for free text, with caps. Urgencias never go through the LLM. Blocked on Mercurio API docs and on knowing who operates the current bot.
- The production agent needs Mercurio data and a client-defined line between orienting and medical advice. The lab prompt is minimal on purpose.

## Conventions

- Conventional commits, in Spanish like the history. No AI attribution or `Co-Authored-By`.
- Code, comments and identifiers in English. User-facing agent text and the README in Spanish.
- Never commit `.env`, `.env.tts` or `certs/*.pem`.
