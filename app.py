
import os
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

# Сохраняем ID обработанных событий, чтобы не удвоить
processed_hooks = set()


@app.get("/")
def root():
    return {"status": "running"}


# === Обработчик входящего вебхука ===
@app.post("/webhook")
async def webhook_listener(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    hook_id = data.get("hash") or data.get("block_hash")
    if not hook_id:
        return JSONResponse({"error": "No unique ID in payload"}, status_code=400)

    # проверяем идемпотентность
    if hook_id in processed_hooks:
        return JSONResponse({"status": "duplicate ignored"}, status_code=200)
    processed_hooks.add(hook_id)

    # ⚡ Твоя бизнес-логика (например, добавить баланс пользователю)
    print("📥 Получено событие:", data)

    return JSONResponse({"status": "ok"}, status_code=200)


# === Удаление старых вебхуков ===
def clear_old_webhooks(token: str):
    url = f"https://api.blockcypher.com/v1/ltc/main/hooks?token={token}"
    r = requests.get(url)
    if r.status_code != 200:
        print("❌ Ошибка при получении списка вебхуков:", r.status_code, r.text)
        return

    hooks = r.json()
    if not hooks:
        print("ℹ️ Старых вебхуков нет")
        return

    for hook in hooks:
        hook_id = hook.get("id")
        if hook_id:
            del_url = f"https://api.blockcypher.com/v1/ltc/main/hooks/{hook_id}?token={token}"
            dr = requests.delete(del_url)
            if dr.status_code == 204:
                print(f"🗑️ Удалён вебхук {hook_id}")
            else:
                print(f"⚠️ Ошибка удаления {hook_id}: {dr.status_code} {dr.text}")


# === Создание нового вебхука ===
def register_webhook(token: str, callback_url: str, address: str, event: str = "confirmed-tx"):
    url = f"https://api.blockcypher.com/v1/ltc/main/hooks?token={token}"
    payload = {
        "event": event,
        "address": address,
        "url": callback_url
    }
    r = requests.post(url, json=payload)
    if r.status_code == 201:
        print("✅ Новый вебхук создан:", r.json())
    elif r.status_code == 200:
        print("ℹ️ Вебхук уже существует:", r.json())
    else:
        print("❌ Ошибка регистрации вебхука:", r.status_code, r.text)


# === Автоматический запуск при старте ===
@app.on_event("startup")
def startup_event():
    token = os.getenv("BLOCKCYPHER_TOKEN")
    address = os.getenv("LTC_ADDRESS")
    service_url = os.getenv("RENDER_EXTERNAL_URL")  # Render подставляет автоматически

    if not token or not address or not service_url:
        print("⚠️ Не заданы BLOCKCYPHER_TOKEN, LTC_ADDRESS или RENDER_EXTERNAL_URL")
        return

    callback_url = f"{service_url}/webhook"

    print("🔄 Удаляем старые вебхуки...")
    clear_old_webhooks(token)

    print(f"🔗 Регистрируем новый вебхук для {address} на {callback_url}")
    register_webhook(token, callback_url, address, event="confirmed-tx")
