"""One asyncio task per call: accept, open the Realtime WebSocket and run the agent."""

import asyncio
import json
import logging

import httpx
import websockets

import agent
import config

log = logging.getLogger("webhook")

API = "https://api.openai.com/v1/realtime"
AUTH = {"Authorization": f"Bearer {config.OPENAI_API_KEY}"}
GOODBYE_DELAY_S = 2.0


def clog(call_id: str, event: str, **fields) -> None:
    """One structured log line per event, always carrying the call_id."""
    log.info(json.dumps({"call_id": call_id, "event": event, **fields}, ensure_ascii=False))


async def _post(http: httpx.AsyncClient, call_id: str, action: str, body: dict | None = None) -> httpx.Response:
    return await http.post(f"{API}/calls/{call_id}/{action}", headers=AUTH, json=body, timeout=15)


async def _send(ws, payload: dict) -> None:
    await ws.send(json.dumps(payload))


async def _run_tool(http, ws, call_id: str, item: dict) -> None:
    name = item.get("name")
    tool_call_id = item.get("call_id")
    try:
        args = json.loads(item.get("arguments") or "{}")
    except ValueError:
        args = {}
    clog(call_id, "tool_call", tool=name)

    output: dict = {"ok": True}
    respond = True
    try:
        if name == "transferir_a_guardia":
            resp = await _post(http, call_id, "refer", {"target_uri": config.TRANSFER_TARGET_URI})
            clog(call_id, "transfer", status=resp.status_code, target=config.TRANSFER_TARGET_URI)
            if resp.status_code >= 300:
                output = {"ok": False, "error": f"refer failed: {resp.status_code}"}
            else:
                respond = False  # the call is leaving; do not speak again
        elif name == "guardar_mensaje":
            clog(
                call_id,
                "message_saved",
                message={k: args.get(k) for k in ("nombre", "telefono", "mascota", "especie", "motivo")},
            )
        elif name == "terminar_llamada":
            await asyncio.sleep(GOODBYE_DELAY_S)
            resp = await _post(http, call_id, "hangup")
            clog(call_id, "hangup", status=resp.status_code)
            return
        else:
            output = {"ok": False, "error": f"unknown tool {name}"}
    except Exception as exc:  # noqa: BLE001 - report any failure back to the model
        clog(call_id, "tool_error", tool=name, error=repr(exc))
        output = {"ok": False, "error": str(exc)}

    await _send(ws, {
        "type": "conversation.item.create",
        "item": {"type": "function_call_output", "call_id": tool_call_id, "output": json.dumps(output)},
    })
    if respond:
        await _send(ws, {"type": "response.create"})


async def _listen(http, ws, call_id: str) -> None:
    tool_tasks: set[asyncio.Task] = set()
    try:
        async for raw in ws:
            try:
                event = json.loads(raw)
            except ValueError:
                continue
            etype = event.get("type")
            if etype == "response.done":
                status = (event.get("response") or {}).get("status")
                clog(call_id, "response_done", status=status)
            elif etype == "response.output_item.done":
                item = event.get("item") or {}
                if item.get("type") == "function_call":
                    task = asyncio.create_task(_run_tool(http, ws, call_id, item))
                    tool_tasks.add(task)
                    task.add_done_callback(tool_tasks.discard)
            elif etype == "error":
                clog(call_id, "realtime_error", error=event.get("error"))
    finally:
        for task in tool_tasks:
            task.cancel()


async def handle_call(call_id: str, sip_headers: list[dict]) -> None:
    """Never raises: any failure is logged and the task ends."""
    hdrs = {h.get("name", "").lower(): h.get("value") for h in sip_headers if isinstance(h, dict)}
    clog(call_id, "incoming", sip_from=hdrs.get("from"), sip_to=hdrs.get("to"))
    try:
        async with httpx.AsyncClient() as http:
            resp = await _post(http, call_id, "accept", agent.accept_body(
                config.OPENAI_REALTIME_MODEL, config.OPENAI_REALTIME_VOICE, config.turn_detection()))
            if resp.status_code >= 300:
                clog(call_id, "accept_failed", status=resp.status_code, body=resp.text[:300])
                return
            clog(call_id, "accepted", status=resp.status_code, turn_detection=config.turn_detection())

            async with websockets.connect(f"wss://api.openai.com/v1/realtime?call_id={call_id}",
                                          additional_headers=AUTH) as ws:
                clog(call_id, "ws_open")
                await _send(ws, {"type": "response.create",
                                 "response": {"instructions": agent.FIRST_RESPONSE_INSTRUCTIONS}})
                await _listen(http, ws, call_id)
            clog(call_id, "ws_closed")
    except asyncio.CancelledError:
        clog(call_id, "cancelled")
        raise
    except Exception as exc:  # noqa: BLE001
        clog(call_id, "call_error", error=repr(exc))
