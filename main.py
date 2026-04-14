if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)from flask import Flask, request
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")


# -----------------------------
# Verificación webhook (Meta)
# -----------------------------
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200

    return "Token inválido", 403


# -----------------------------
# Recibir mensajes WhatsApp
# -----------------------------
@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()

    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        messages = value.get("messages")

        if messages:
            message = messages[0]
            from_number = message["from"]

            text = ""
            if message.get("type") == "text":
                text = message["text"]["body"]

            print("Mensaje recibido:", text)

            reply_text = get_reply(text)

            send_whatsapp_message(from_number, reply_text)

        return {"status": "ok"}, 200

    except Exception as e:
        print("Error:", str(e))
        return {"status": "error", "detail": str(e)}, 200


def get_reply(text: str):
    text_lower = text.lower()

    if "precio" in text_lower or "cuánto cuesta" in text_lower or "cuanto cuesta" in text_lower:
        return (
            "Claro. Para darte un precio exacto necesito 2 datos:\n"
            "1) ¿Tu estudio ya tiene logo e identidad visual?\n"
            "2) ¿Cuántos proyectos quieres mostrar en la web? (aprox.)"
        )

    if "hola" in text_lower or "buenas" in text_lower:
        return (
            "Hola 👋 Soy el asesor digital.\n\n"
            "¿Buscas una página web profesional para captar clientes o para mostrar portafolio?"
        )

    return (
        "Perfecto. Para orientarte bien:\n"
        "¿Tu estudio ya tiene página web actualmente o sería desde cero?"
    )


def send_whatsapp_message(to_number: str, message_text: str):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message_text}
    }

    response = requests.post(url, headers=headers, json=payload)

    print("Respuesta API:", response.status_code, response.text)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

