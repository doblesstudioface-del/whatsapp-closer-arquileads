from flask import Flask, request
import requests
import os

app = Flask(__name__)

ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
GRAPH_API_VERSION = os.environ.get("GRAPH_API_VERSION", "v25.0")


def normalizar_texto(texto):
    return (texto or "").strip().lower()


def obtener_respuesta_arquileads(mensaje):
    texto = normalizar_texto(mensaje)

    if any(p in texto for p in ["precio", "cuanto", "cuánto", "costo", "vale", "paquete"]):
        return (
            "Claro. Para recomendarte el paquete correcto necesito 3 datos:\n\n"
            "1. ¿Qué vendes: arquitectura, interiores, bienes raíces u otro servicio?\n"
            "2. ¿Ya tienes página web o empezamos desde cero?\n"
            "3. ¿Quieres solo landing o también automatización de WhatsApp?"
        )

    if any(p in texto for p in ["landing", "pagina", "página", "web", "sitio"]):
        return (
            "Perfecto. Una landing de Arquileads puede ayudarte a convertir visitantes en contactos por WhatsApp.\n\n"
            "Incluye propuesta clara, servicios, testimonios, botón a WhatsApp y llamadas a la acción.\n\n"
            "¿La quieres para arquitectura, interiores o bienes raíces?"
        )

    if any(p in texto for p in ["whatsapp", "bot", "automatizar", "automático", "automatico", "responder"]):
        return (
            "Sí, podemos automatizar WhatsApp para responder leads al instante.\n\n"
            "El flujo recomendado es:\n"
            "1. saludar al lead\n"
            "2. preguntar qué servicio busca\n"
            "3. calificar presupuesto y urgencia\n"
            "4. llevarlo a llamada o cotización\n\n"
            "¿Quieres que el bot venda, califique o agende llamadas?"
        )

    if any(p in texto for p in ["hola", "buenas", "info", "informacion", "información"]):
        return (
            "¡Hola! Soy el asistente de Arquileads. 👋\n\n"
            "Ayudamos a negocios de arquitectura, interiores y bienes raíces a captar y responder leads por WhatsApp.\n\n"
            "¿Buscas una landing, automatizar WhatsApp o conseguir más clientes?"
        )

    return (
        "Gracias por escribirme. Para ayudarte mejor, dime cuál de estas opciones buscas:\n\n"
        "1. Crear una landing page premium\n"
        "2. Automatizar respuestas de WhatsApp\n"
        "3. Captar más clientes para arquitectura/interiores\n\n"
        "Respóndeme con el número o cuéntame tu caso."
    )


@app.route("/", methods=["GET"])
def home():
    return "Arquileads WhatsApp closer activo", 200


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if token == VERIFY_TOKEN:
            return challenge or "", 200

        return "Error de verificación", 403

    data = request.get_json(silent=True) or {}
    print(f"Webhook recibido: {data}")

    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])

                for message in messages:
                    number = message.get("from")
                    message_type = message.get("type")

                    if not number:
                        continue

                    if message_type != "text":
                        enviar_mensaje(
                            number,
                            "Gracias por tu mensaje. Por ahora puedo responder mejor si me escribes en texto. ¿Qué necesitas lograr con Arquileads?"
                        )
                        continue

                    message_body = message.get("text", {}).get("body", "")
                    print(f"Mensaje recibido de {number}: {message_body}")

                    respuesta = obtener_respuesta_arquileads(message_body)
                    enviar_mensaje(number, respuesta)

    except Exception as e:
        print(f"Error procesando webhook: {e}")

    return "EVENT_RECEIVED", 200


def enviar_mensaje(number, text):
    if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
        print("Faltan ACCESS_TOKEN o PHONE_NUMBER_ID en variables de entorno")
        return

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": number,
        "type": "text",
        "text": {"body": text}
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        print(f"Respuesta de Meta: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        print(f"Error enviando mensaje a Meta: {e}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))