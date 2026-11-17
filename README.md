# vet24-sip-lab

> **Estado: nada de esto se ha ejecutado todavía.** Los archivos se escribieron y se verificaron de forma estática (sintaxis y análisis). La primera corrida real puede revelar ajustes; ver "Pendientes de verificar en la primera corrida".

## Qué es

Laboratorio en Docker que **emula el comportamiento SIP de la central ZYCOO CooVox-T100** de Vet24 (no su firmware). Se usa para probar, antes de tener acceso al equipo real, la conexión por "SIP directo" (troncal SIP de la central al proveedor de voz con IA, sin Twilio) con tres candidatos: OpenAI, ElevenLabs Agents y LiveKit Cloud.

Un contenedor Asterisk 20 hace lo siguiente:

- Llama por troncal SIP (TLS + SRTP) a cada proveedor.
- Recibe las transferencias REFER que devuelve el agente.
- Cae al buzón de voz si el proveedor no atiende.
- Aplica la regla horaria 21:00-09:00 con feriados.
- Graba cada llamada con pistas separadas de llamante y agente para medir latencia.
- Ejecuta llamadas de prueba guionadas con voces sintetizadas.

## Arquitectura

```
 Softphone (humano) ──UDP 5060──┐
                                │
 Llamante guionado              ▼
 (Local channel, .sln16) ─▶ ┌──────────────────────────┐   TLS 5061 + SRTP    ┌──────────────┐
                            │  Asterisk "T100"         │ ───────────────────▶ │ OpenAI       │
                            │  [central] regla horaria │ ───────────────────▶ │ ElevenLabs   │
                            │  [sub-dial-provider]     │ ───────────────────▶ │ LiveKit      │
                            │  MixMonitor (2 pistas)   │                      └──────┬───────┘
                            └────┬──────────────┬──────┘                             │
                                 │              ▲                                    │
                  sin respuesta  │              └──── REFER (urgencias) ─────────────┘
                  o timeout      ▼                    cae en [from-provider] y
                          Buzón de voz 9000@lab       suena el softphone
```

Entrada de llamadas:

- `1`, `2`, `3` desde el softphone llaman directo a OpenAI, ElevenLabs y LiveKit (flujo `manual`).
- `100` simula marcar el número de la clínica y pasa por la regla horaria `[central]`.

## Requisitos

- VPS Linux con IP pública, Docker y Docker Compose. Se usa el VPS de LambdaWorks en São Paulo (más cerca del recorrido real de la T100 en Rosario que un servidor en EE.UU.). Corre fuera del Hub, clonado en el home del usuario `lambdaworks` (por ejemplo `~/vet24-sip-lab`); las reglas de firewall, el DNS y el certificado los configura un admin del servidor.
- Puertos abiertos:
  - `5060/udp`: solo desde la IP del softphone.
  - `5061/tcp`: señalización TLS (los proveedores pueden abrir conexiones nuevas hacia esta IP).
  - `10000-10199/udp`: RTP.
- Certificado confiable para `LAB_FQDN` (por ejemplo con certbot), copiado como `certs/fullchain.pem` y `certs/privkey.pem`. Sin ellos se genera uno autofirmado: las llamadas salientes funcionan, pero los BYE/REFER que ElevenLabs inicia en una conexión nueva requieren un certificado válido para un FQDN. Tras renovar el certificado, reiniciar el contenedor.
- Por proveedor:
  - **OpenAI**: un servicio webhook que acepte la llamada entrante (OpenAI llama a ese webhook). **No forma parte de este laboratorio; es el siguiente paso.** La URI de destino es `sip:<PROJECT_ID>@sip.api.openai.com;transport=tls`, puerto 5061, solo TLS, SRTP (SDES) obligatorio.
  - **ElevenLabs**: un agente con un número SIP importado (E.164 con `+`). Host `sip.rtc.elevenlabs.io`, TLS 5061, TLS 1.2 o superior. La opción de cifrado de medios del número (Disabled/Allowed/Required) debe coincidir con `ELEVENLABS_MEDIA_ENCRYPTION`.
  - **LiveKit Cloud**: inbound trunk con `numbers` en E.164, dispatch rule y un agent worker. La opción de SRTP del trunk (allow/require) debe coincidir con `LIVEKIT_MEDIA_ENCRYPTION`.
- Para generar voces: `python3` y una `OPENAI_API_KEY` en `.env.tts` (se copia de `.env.tts.example`). Solo la lee `generate_prompts.py` en el host; no llega al contenedor de Asterisk.
- Para medir latencia: `python3` en el host.

## Configuración

```bash
cp .env.example .env   # completar y no subir nunca al repositorio
cp .env.tts.example .env.tts   # OPENAI_API_KEY, TTS_MODEL, TTS_VOICE (voz por defecto coral); solo para el host
```

| Variable | Descripción |
| --- | --- |
| `PUBLIC_IP` | IP pública del VPS (obligatoria). |
| `LAB_FQDN` | FQDN con certificado confiable; por defecto `PUBLIC_IP`. |
| `SOFTPHONE_USER` / `SOFTPHONE_PASSWORD` | Credenciales del softphone (contraseña obligatoria; evitar `;` y `$`). |
| `VOICEMAIL_PIN` | PIN del buzón 9000 (obligatorio). |
| `LAB_CALLER_ID` | Caller ID ficticio hacia los proveedores (obligatorio). |
| `TIME_MODE` | `auto`, `night` o `day`. |
| `OFFICE_HOURS` | Rango diurno, por defecto `09:00-20:59`. |
| `NIGHT_PROVIDER` | Proveedor de la rama nocturna: `openai`, `elevenlabs` o `livekit`. |
| `PROVIDER_ANSWER_TIMEOUT` | Segundos de espera antes de desviar al buzón. |
| `AGENT_TURN_TIMEOUT` | Segundos máximos que el llamante guionado espera al agente. |
| `BARGE_DELAY` | Segundos tras oír al agente antes de interrumpirlo. |
| `RTP_START` / `RTP_END` | Rango RTP. |
| `OPENAI_PROJECT_ID` | Habilita el proveedor `openai`. |
| `ELEVENLABS_NUMBER` | Habilita `elevenlabs`. Número E.164 con `+`. |
| `ELEVENLABS_SIP_USER` / `_PASSWORD` | Digest opcional. |
| `ELEVENLABS_MEDIA_ENCRYPTION` | `sdes` o `no`. |
| `LIVEKIT_SIP_HOST` | Habilita `livekit` (por ejemplo `<subdominio>.sip.livekit.cloud`). |
| `LIVEKIT_NUMBER` | Número E.164 del trunk. |
| `LIVEKIT_SIP_USER` / `_PASSWORD` | Autenticación del trunk (opcional). |
| `LIVEKIT_MEDIA_ENCRYPTION` | `sdes` o `no`. |

`generate_prompts.py` guarda el texto de cada frase en `prompts/raw/<flujo>/NN.txt`: si el texto del flujo cambia se regenera el audio, y se eliminan los `NN.*` sobrantes (`--dry-run` muestra qué haría sin llamar a la API). `lab.sh prompts` también elimina los `.sln16`/`.barge` huérfanos.

Solo se genera la configuración SIP de los proveedores cuyas variables estén completas. Los feriados se editan en `config/feriados.txt` (solo contiene los feriados nacionales fijos de 2026 y 2027; los móviles y puentes deben completarse; la lista real es una pregunta abierta para Vet24).

## Uso

```bash
scripts/lab.sh up                        # construye y levanta (lo ejecuta una persona)
scripts/lab.sh logs                      # logs de Asterisk
scripts/lab.sh cli                       # consola de Asterisk
scripts/lab.sh prompts                   # genera voces (TTS) y convierte a .sln16
scripts/lab.sh call openai saludo        # una llamada guionada
scripts/lab.sh suite elevenlabs          # todos los flujos, uno por vez
scripts/lab.sh suite livekit turno urgencias
scripts/lab.sh latency                   # latencia sobre recordings/
scripts/lab.sh down
```

Los flujos están en `tests/flows/*.txt`: las líneas `# espera:` describen el comportamiento esperado del agente, cada otra línea es lo que dice el llamante y el prefijo `>` marca una interrupción (barge-in). Los nombres de flujo usan solo letras `a-z`.

Códigos de marcado desde el softphone (registrar contra `PUBLIC_IP:5060`, UDP):

| Código | Acción |
| --- | --- |
| `1` / `2` / `3` | Llamada manual grabada a OpenAI / ElevenLabs / LiveKit. |
| `100` | Número principal de la clínica, vía regla horaria. |
| `*98` | Buzón de voz (mailbox 9000). |
| `600` | Echo, para verificar el audio. |

Para emular las 3 a.m. a cualquier hora, poner `TIME_MODE=night` en `.env` y reiniciar (`docker compose up -d`); `day` fuerza la rama diurna. Los archivos grabados quedan en `recordings/` con el nombre `<proveedor>-<flujo>-<fecha>-<hora>-<id>-{mix,caller,agent}.wav`; pertenecen al usuario del contenedor y son legibles desde el host.

## Qué mide cada prueba

| Control del plan | Cómo se prueba |
| --- | --- |
| Entrada y códec | `1`/`2`/`3` o `call`; en la CLI, `pjsip show channelstats` y `core show channel` muestran el códec negociado (g722, ulaw o alaw) y SRTP. |
| Caller ID (From / P-Asserted-Identity) | `pjsip set logger on` y revisar el INVITE: `LAB_CALLER_ID` en From y P-Asserted-Identity. |
| REFER a urgencias | Flujo `urgencias`: el agente envía REFER, la llamada cae en `[from-provider]` y suena el softphone. |
| Desvío al buzón | Dejar un proveedor sin configurar o inalcanzable: tras `PROVIDER_ANSWER_TIMEOUT` la llamada va a `9000@lab`; se escucha con `*98`. |
| Horario y feriados | `TIME_MODE=auto` con `100`, y fechas de `feriados.txt`; `night` y `day` para forzar la rama. |
| Latencia | `scripts/lab.sh latency`: respuesta del agente (inicio de su voz menos fin de la del llamante), mediana, p95 y máximo por proveedor. Mide el lado de la central y excluye la diferencia de red entre Rosario y São Paulo, que se mide en la ventana con el T100. |
| Guion | `suite`: los flujos cubren saludo, horarios, precios, turnos, urgencias, internados, Movet, mensaje, encuesta, interrupciones y ruido. |
| Voces | `prompts` con distintos `TTS_VOICE`; el flujo `ruido` agrega ruido de fondo en la conversión. |

## Seguridad

- Firewall: `5060/udp` solo desde la IP del softphone (no hay endpoint anónimo, pero conviene no exponerlo); `5061/tcp` y `10000-10199/udp` abiertos. Para OpenAI se pueden restringir los medios a: `13.79.45.80/28`, `23.98.140.64/28`, `40.67.149.176/28`, `40.83.204.240/28`. Para el resto de los proveedores, consultar sus rangos vigentes.
- Usar contraseñas largas y aleatorias para el softphone y el buzón.
- No subir `.env`, certificados ni grabaciones (están en `.gitignore`).
- Las grabaciones contienen voz de las pruebas; tratarlas como datos sensibles.

## Pendientes de verificar en la primera corrida

- **MixMonitor**: confirmar que `-agent.wav` contiene la voz del agente y `-caller.wav` la del llamante (mapeo `r`/`t` en el canal saliente). Sin relleno de silencio, los archivos `r`/`t` pueden desalinearse en el tiempo; por eso los resultados de `measure_latency.py` deben contrastarse con el archivo `-mix.wav` en la primera corrida.
- **Conversión con sox**: confirmar que `prompts` genera `.sln16` reproducibles (`Playback(lab/<flujo>/NN)`) y que la mezcla de ruido del flujo `ruido` tiene un nivel razonable.
- **Sonidos en español**: el Dockerfile instala `asterisk-core-sounds-es-g722` (nombre confirmado con `apt-cache` en el host, versión 1.6.1-1) y `asterisk-core-sounds-en`. Falta confirmar la ruta que usa Asterisk y que el buzón de voz suene en español.
- **Enlaces de sonidos**: el entrypoint enlaza `/usr/share/asterisk/sounds/lab` (y `/var/lib/asterisk/sounds/lab` si ese directorio existe) a `/lab/prompts/asterisk`; el dialplan consulta la primera ruta con `STAT`. El Dockerfile enlaza `sounds/es` y `sounds/en` a los directorios `es_MX_f_Allison` y `en_US_f_Allison` si existen; verificar ambos.
- **Configuración base de Asterisk**: el laboratorio no reemplaza `asterisk.conf` y usa el del paquete Debian/Ubuntu.
- **Rechazo de INVITE ajenos**: los endpoints de proveedor usan `identify_by=auth_username`. Probar con un INVITE de prueba fuera de diálogo con From `openai`, `elevenlabs` o `livekit` y confirmar que se rechaza.
- **Certificado en ElevenLabs**: ElevenLabs valida el certificado TLS contra el host del Contact. Con `external_signaling_address=PUBLIC_IP` el Contact lleva la IP y un certificado emitido para `LAB_FQDN` podría no coincidir. Revisar en la primera corrida y considerar `external_signaling_address=${LAB_FQDN}` (no está verificado que Asterisk acepte un nombre de host ahí).
- **Tiempo de `channel originate`**: tiene un tiempo de espera fijo de unos 30 s; un `PROVIDER_ANSWER_TIMEOUT` superior a unos 25 s no extiende las llamadas guionadas.
- **Negociación SRTP** por proveedor (SDES, claves en el SDP) y que el proveedor acepte `tlsv1_2` y el SNI.
- **Endpoint del softphone**: la sección se llama como `SOFTPHONE_USER` (no `softphone`) para que Asterisk lo identifique por usuario SIP.
- Ownership de `recordings/`: el entrypoint cambia el propietario del directorio al usuario `asterisk` del contenedor.
