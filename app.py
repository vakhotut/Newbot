#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
app.py

FastAPI + Telegram bot + BlockCypher LTC webhook.

Функционал:
- При старте очищает старые вебхуки BlockCypher и регистрирует новый для LTC-адреса.
- Обрабатывает входящие вебхуки BlockCypher на /webhook.
- Поднимает Telegram webhook на /telegram_webhook:
    - /start показывает LTC-адрес и кнопки.
    - Кнопка "Проверить транзакции" — проверяет через BlockCypher и выдаёт список последних tx.
    - Кнопка "Показать LTC адрес" — выводит твой адрес.
"""

import os
import json
import threading
import time
from typing import Optional, List, Dict, Any

import requests
from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse

# ------- Конфигурация -------
BLOCKCYPHER_BASE = "https://api.blockcypher.com/v1/ltc/main"
REQUEST_TIMEOUT = 10  # секунд для HTTP запросов к BlockCypher
PROCESSED_STORE_FILE = os.getenv("PROCESSED_STORE_FILE", "processed_hooks.json")
PERSIST_PROCESSED = os.getenv("PERSIST_PROCESSED", "1") != "0"

TELEGRAM_API_BASE = "https://api.telegram.org"

# ------- Инициализация -------
app = FastAPI()
processed_hooks_lock = threading.Lock()
try:
    if PERSIST_PROCESSED and os.path.exists(PROCESSED_STORE_FILE):
        with open(PROCESSED_STORE_FILE, "r", encoding="utf-8") as f:
            processed_hooks = set(json.load(f))
    else:
        processed_hooks = set()
except Exception:
    processed_hooks = set()


def persist_processed_hooks():
    if not PERSIST_PROCESSED:
        return
    try:
        with processed_hooks_lock:
            with open(PROCESSED_STORE_FILE, "w", encoding="utf-8") as f:
                json.dump(list(processed_hooks), f)
    except Exception as e:
        print("❌ Ошибка при сохранении processed_hooks:", e)


# ------- BlockCypher API -------
def list_webhooks(token: str) -> Optional[List[Dict[str, Any]]]:
    try:
        url = f"{BLOCKCYPHER_BASE}/hooks?token={token}"
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.json() or []
        print("⚠️ Ошибка получения вебхуков:", r.status_code, r.text)
    except Exception as e:
        print("⚠️ Exception in list_webhooks:", e)
    return None


def delete_webhook(token: str, hook_id: str) -> bool:
    try:
        url = f"{BLOCKCYPHER_BASE}/hooks/{hook_id}?token={token}"
        r = requests.delete(url, timeout=REQUEST_TIMEOUT)
        return r.status_code in (200, 204)
    except Exception as e:
        print("⚠️ Exception in delete_webhook:", e)
    return False


def clear_old_webhooks(token: str):
    hooks = list_webhooks(token)
    if not hooks:
        print("ℹ️ Старых вебхуков нет")
        return
    for hook in hooks:
        hid = hook.get("id")
        if hid and delete_webhook(token, hid):
            print(f"🗑️ Удалён вебхук {hid}")


def register_webhook(token: str, callback_url: str, address: str, event="confirmed-tx", signkey=None):
    try:
        url = f"{BLOCKCYPHER_BASE}/hooks?token={token}"
        payload = {"event": event, "address": address, "url": callback_url}
        if signkey:
            payload["signkey"] = signkey
        r = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        if r.status_code in (200, 201):
            print("✅ Вебхук зарегистрирован:", r.text)
            return r.json()
        else:
            print("❌ Ошибка регистрации вебхука:", r.status_code, r.text)
    except Exception as e:
        print("❌ Exception in register_webhook:", e)
    return None


# ------- Telegram helpers -------
def telegram_api_call(token: str, method: str, payload: dict) -> Dict[str, Any]:
    url = f"{TELEGRAM_API_BASE}/bot{token}/{method}"
    try:
        r = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def tg_send_message(token: str, chat_id: int, text: str, reply_markup: Optional[dict] = None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return telegram_api_call(token, "sendMessage", payload)


def tg_answer_callback(token: str, callback_query_id: str, text: Optional[str] = None, show_alert=False):
    payload = {"callback_query_id": callback_query_id, "show_alert": show_alert}
    if text:
        payload["text"] = text
    return telegram_api_call(token, "answerCallbackQuery", payload)


# ------- Маршруты -------
@app.get("/")
def root():
    return {"status": "running"}


@app.post("/webhook")
async def webhook_listener(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    hook_id = data.get("hash") or data.get("block_hash") or data.get("id") or str(time.time())
    with processed_hooks_lock:
        if hook_id in processed_hooks:
            return JSONResponse({"status": "duplicate"}, status_code=200)
        processed_hooks.add(hook_id)
        persist_processed_hooks()

    print("📥 Получено событие BlockCypher:", data)
    # TODO: твоя бизнес-логика (например, обновить баланс пользователя)

    return JSONResponse({"status": "ok"}, status_code=200)


@app.post("/telegram_webhook")
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: Optional[str] = Header(None)):
    TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    SECRET = os.getenv("TELEGRAM_SECRET_TOKEN")
    if not TG_TOKEN:
        return JSONResponse({"error": "TELEGRAM_BOT_TOKEN not set"}, status_code=500)
    if SECRET and x_telegram_bot_api_secret_token != SECRET:
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    update = await request.json()
    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")
        if text.startswith("/start"):
            addr = os.getenv("LTC_ADDRESS", "[NOT_SET]")
            kb = {"inline_keyboard": [
                [{"text": "Проверить транзакции", "callback_data": "check_txs"}],
                [{"text": "Показать LTC адрес", "callback_data": "show_addr"}],
            ]}
            msg = f"👋 Привет!\n\nТвой LTC-адрес:\n<code>{addr}</code>"
            tg_send_message(TG_TOKEN, chat_id, msg, kb)
        return {"ok": True}

    if "callback_query" in update:
        cq = update["callback_query"]
        data = cq["data"]
        chat_id = cq["message"]["chat"]["id"]
        cqid = cq["id"]
        tg_answer_callback(TG_TOKEN, cqid)
        if data == "show_addr":
            addr = os.getenv("LTC_ADDRESS", "[NOT_SET]")
            tg_send_message(TG_TOKEN, chat_id, f"📫 LTC адрес:\n<code>{addr}</code>")
        if data == "check_txs":
            addr = os.getenv("LTC_ADDRESS")
            token = os.getenv("BLOCKCYPHER_TOKEN")
            url = f"{BLOCKCYPHER_BASE}/addrs/{addr}/full"
            if token:
                url += f"?token={token}"
            r = requests.get(url, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                txs = r.json().get("txs", [])[:5]
                lines = []
                for tx in txs:
                    h = tx.get("hash")
                    conf = tx.get("confirmations", 0)
                    lines.append(f"🔸 <code>{h}</code> · {conf} подтверждений")
                if not lines:
                    tg_send_message(TG_TOKEN, chat_id, "ℹ️ Нет транзакций.")
                else:
                    tg_send_message(TG_TOKEN, chat_id, "\n\n".join(lines))
            else:
                tg_send_message(TG_TOKEN, chat_id, "❌ Ошибка запроса транзакций")
        return {"ok": True}

    return {"ok": True}


# ------- Startup -------
@app.on_event("startup")
def startup_event():
    token = os.getenv("BLOCKCYPHER_TOKEN")
    address = os.getenv("LTC_ADDRESS")
    service_url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("SERVICE_URL")
    if token and address and service_url:
        cb_url = service_url.rstrip("/") + "/webhook"
        clear_old_webhooks(token)
        register_webhook(token, cb_url, address, "confirmed-tx", os.getenv("BLOCKCYPHER_SIGNKEY"))
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if tg_token:
        print("ℹ️ Telegram webhook URL:",
              (os.getenv("RENDER_EXTERNAL_URL") or "https://your-app.onrender.com").rstrip("/") + "/telegram_webhook")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
