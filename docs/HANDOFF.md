# HANDOFF — Vet24 after-hours assistant

Read first: `CLAUDE.md` (repo context, layout, ops, gotchas). Then this file. Then run the Hub's `get_context` with `git remote get-url origin` (Hub project **Vet24**, id `ba39bd9b-052c-41c0-9274-14dba144d089`).

## The user and how to work with them
- LambdaWorks dev (Rosario). Replies in **rioplatense Spanish**, short. Ask one question at a time, then stop.
- **Ask before every commit or push.** Commits are conventional, **in Spanish**, with **no Co-Authored-By/AI attribution**. Push to `main`, then mirror to `develop` (`git push origin main:develop`).
- **Secrets never go through chat**: API keys and webhook secrets are loaded by the user (Hub UI, `.env` files, CLI login).
- **VPS: the user runs the commands and pastes output.** User `lambdaworks`, no sudo, no Hestia admin panel. Firewall/DNS/cert changes need a server admin.

## The project
Vet24 is a vet clinic in Rosario. From 21:00 to 09:00 and on holidays it wants AI handling on two channels:
1. **Phone:** its ZYCOO **CooVox-T100** PBX (operated by **Faxtel**) sends night calls by SIP directly (no Twilio) to an AI voice agent.
2. **WhatsApp:** the existing bot (fixed menu; "Pedir turno" → "Autogestionar" = Mercurio's online booking) must offer the same functionality as the night call.

The clinic's system is **Mercurio**. LambdaWorks does not own it; all data is read and written via **Mercurio's APIs**. The user confirmed they exist for availability and appointment creation. Repo `Lambda-Works/vet24` was only the 48 h sales prototype.

## Final decisions (do not re-litigate)
| Date | Decision |
| --- | --- |
| 2026-11-20 | **Voice provider: ElevenLabs Agents.** See the lab results below. |
| 2026-11-20 | WhatsApp: deterministic buttons for menu and booking, which write to Mercurio. A **cheap LLM (DeepSeek-like)** handles free text only: it classifies and extracts, then hands off to the button flows. Per-conversation cap and daily budget alarm. **Urgencias never go through the LLM** (fixed MENDOZA 1960 24 h text). Raise with the client: DeepSeek means an international personal-data transfer (Ley 25.326). |
| 2026-11-20 | Channels have **functional parity**, not a shared implementation. Scope = the 10 text-applicable flows in `tests/flows/*.txt`; each `# espera` is the acceptance criterion. |
| 2026-11-06 | Lab provider accounts belong to LambdaWorks, with a low spend limit. |
| 2026-11-06 | The SIP lab runs **by hand** on the shared Hub VPS (72.61.50.55, São Paulo), outside the Hub. The user chose this knowingly. |
| 2026-11-19 | The OpenAI webhook replaced the prototype in Vet24 Hub **development**. It is kept only as a reference; don't extend it. |

## Lab results that drove the provider decision (2026-11-20)
Manual calls with the same prompt and script, G.711 on the caller leg, from the emulated PBX in São Paulo:

| Provider | Median | p95 | Turns | Notes |
| --- | --- | --- | --- | --- |
| ElevenLabs Agents | 1070 ms | 1821 ms | 8 | More natural voice; stable |
| OpenAI Realtime (default VAD) | 2060 ms | 2416 ms | 5 | More artificial voice |
| OpenAI Realtime (server_vad 300 ms) | 1940 ms | 2256 ms | 5 | Only −120 ms; it cut itself off on short pauses |

Both providers handled greeting, message taking, barge-in and the urgency transfer by REFER end to end. The Rosario → provider leg is unmeasured; it gets measured in the T100 window.

## Where everything lives
| What | Where |
| --- | --- |
| **Plan doc** (to be rebuilt) | https://claude.ai/artifact/Tun2eGWMZvvg4CBmNFg28t, "Vet24 · Plan del asistente fuera de horario (v1)", doc id `d9ec07e8-4110-4b9d-a828-dfd89b66b105`, body node `af140579-0e4b`, rev 26. Read and edit only with the Claude Docs tools (load the `anthropic-skills:docs` skill first). |
| Second, older artifact | https://claude.ai/artifact/NcWe86zVo2r1CEvMAtWtc5 (not reviewed this session) |
| Client inputs | `~/Descargas/Presupuesto_ Vet24 Interno.pdf` (agreed budget), `~/Descargas/CooVox-T100_Datasheet_v1.0.0.pdf`. In Hub Drive: budgets v1–v3 + Interno, transcripts "Meet 1" and "Meet 2". |
| Hub memories | Repo ↔ project mapping; the ElevenLabs decision. |
| Local memory | `~/.claude/projects/-home-bussa-Escritorio-LambdaWorks-vet24-sip-lab/memory/` (context, status, WhatsApp plan) |

### Plan doc: what is current vs outdated
- **Added this session, current:**
  - "Decisión: ElevenLabs"
  - "Ventana con la T100: pasos y preguntas a Faxtel" (11 steps, 15 questions)
  - "Bot de WhatsApp fuera de horario"
  - "Próximos pasos" (owner table)
  - LambdaWorks decision ticked
  - Changelog v1.3
- **Still from v1/v1.1/v1.2, to be rewritten with the real decisions:**
  - Resumen
  - "Lo que ya …" (conditions table)
  - Arquitectura (diagram "dos canales, un núcleo": now functional parity, data only via Mercurio)
  - "Contrato con Mercurio" (7 endpoints; keep it, reconcile with the 10 flows)
  - "Opciones de voz" (OpenAI / Grok / ElevenLabs / LLM propio: now decided)
  - Criterios
  - "Etapa previa" (lab: now done)
  - "Plan por semanas" (timeline + week 1–2 checklists)
  - "Horas y costos" (340 h + cost tables: re-estimate with ElevenLabs pricing and SIP directo, no Twilio)
  - Riesgos
  - Decisiones (Vet24 / Faxtel / Desarrollo lists; the Faxtel list overlaps with the new questions table)
  - Anexo latencia (replace estimates with the measured numbers)
- The "Próximos pasos" table and the pending item "Comunicar en el informe el cambio de Twilio a SIP directo y la nueva estimación de costos" feed the rebuild.

## Current state of the work
- **SIP lab:** working on the VPS. Softphone over **TLS 5061** (`1001@sip-lab.lambdaworks.ar`). The admin opened 5060/udp only for an old IP. Extensions: `1` OpenAI, `2` ElevenLabs, `100` time rule, `600` echo, `*98` voicemail. Recordings are `.wav16`, measured with `scripts/lab.sh latency`. Latest commit: `e4477eb`.
- **ElevenLabs lab agent:**
  - "Vet24 Lab - Fuera de horario": minimal prompt (urgencias → REFER to `sip:urgencias@sip-lab.lambdaworks.ar`, otherwise take a message), configured by hand in the panel.
  - SIP number `+5493410000099`, id `phnum_6301m7mpfnwwewq9fjav9x78py2q`. Inbound config: media encryption disabled, allowed IP `72.61.50.55/32`, remote domain `sip-lab.lambdaworks.ar`.
- **ElevenLabs as code (in progress, uncommitted until this handoff's commit):**
  - `elevenlabs/` initialized with the official CLI `@elevenlabs/cli@1.9.0` (pinned).
  - `elevenlabs/phone_number.json` holds the SIP number config.
  - `scripts/elevenlabs.sh` wraps the CLI: `auth`, `pull --agent`, `status`, `push [--dry-run]`, `phone-show`, `phone-apply`, `cli`. The phone update was validated with `--dry-run`.
  - Next: the user runs `scripts/elevenlabs.sh auth login` and gives the agent id (`agent_...`). Then `pull`, review, `push --dry-run` must be clean, add `agent_id` to `phone_number.json`, README section, `CLAUDE.md` layout row.
- **OpenAI webhook:** Hub Vet24 development, release 11 / v0.2.6+ (`server_vad` 300 ms). Live at `https://dev.vet24.api.lambdaworks.ar/openai/webhook`. Reference only.
- **Unknown untracked dir `.atl/`** in the repo: not ours; ask the user.

## Open items / blockers (external)
1. **Faxtel:** send the 15 questions and get a date for the T100 window (critical path).
2. **Mercurio:** API docs and credentials. They block the production agent and the WhatsApp bot.
3. **Vet24 product definitions:**
   - What the agent may *orient* (reason for visit → specialty) without medical advice. The minimal lab agent sends everything to admin by design.
   - The fixed texts not available from Mercurio (urgencias, Movet, internados report).
   - Who operates the current WhatsApp bot, and where admin receives messages.
4. **Client report:** the switch from Twilio to SIP directo with ElevenLabs, plus new costs.
5. Shut down the VPS Asterisk when not testing (it exposes ports).

## Prompt to paste in the new session
> Leé `docs/HANDOFF.md` y `CLAUDE.md`, corré `get_context` del Hub con el remoto de este repo y cargá la skill de docs. Después rearmá el plan (https://claude.ai/artifact/Tun2eGWMZvvg4CBmNFg28t) con las decisiones reales: ElevenLabs por SIP directo, WhatsApp con paridad funcional vía APIs de Mercurio y DeepSeek solo para texto libre, el laboratorio ya hecho y los resultados medidos. Reescribí las secciones desactualizadas que lista el handoff (incluidos horas y costos sin Twilio) y no inventes datos: lo que falte, dejalo como pregunta abierta. Antes de editar el doc, mostrame la estructura nueva.
