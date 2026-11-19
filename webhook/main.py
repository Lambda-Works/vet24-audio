"""FastAPI webhook receiver for OpenAI Realtime SIP calls."""

import asyncio
import json
import logging

import openai
from fastapi import FastAPI, Request, Response
from openai import OpenAI

import config
from call import handle_call

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("webhook")

app = FastAPI()
client = OpenAI(api_key=config.OPENAI_API_KEY, webhook_secret=config.OPENAI_WEBHOOK_SECRET)

_seen_webhooks: set[str] = set()
_tasks: set[asyncio.Task] = set()


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


@app.post("/openai/webhook")
async def openai_webhook(request: Request) -> Response:
    raw = await request.body()
    try:
        client.webhooks.unwrap(raw, request.headers)
    except (openai.InvalidWebhookSignatureError, ValueError):
        return Response(status_code=400)

    webhook_id = request.headers.get("webhook-id", "")
    if webhook_id in _seen_webhooks:
        return Response(status_code=200)
    if webhook_id:
        _seen_webhooks.add(webhook_id)

    try:
        event = json.loads(raw)
    except ValueError:
        return Response(status_code=400)
    if event.get("type") != "realtime.call.incoming":
        return Response(status_code=200)

    data = event.get("data") or {}
    call_id = data.get("call_id")
    if not call_id:
        return Response(status_code=200)

    task = asyncio.create_task(handle_call(call_id, data.get("sip_headers") or []))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return Response(status_code=200)
