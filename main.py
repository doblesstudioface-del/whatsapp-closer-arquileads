from flask import Flask, request
import requests
import os

app = Flask(__name__)

# Configuración de variables (Render ya las tiene)
ACCESS_TOKEN = os.environ.get('ACCESS_TOKEN')
PHONE_NUMBER_ID = os.environ.get('PHONE_NUMBER_ID')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "Error de verificación", 403

    # Aquí recibimos el mensaje de WhatsApp
    data = request.get_json()
    try:
        if data.get("entry"):
            for entry in data["entry"]:
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if "messages" in value:
                        number = value["messages"][0]["from"]
                        message_body = value["messages"][0]["text"]["body"]
                        
                        # LOG para ver el mensaje en Render
                        print(f"Mensaje recibido de {number}: {message_body}")

                        # RESPUESTA AUTOMÁTICA
                        enviar_mensaje(number, f"¡Hola! Soy tu asistente de Arquileads. Recibí tu mensaje: '{message_body}'. ¿En qué puedo ayudarte hoy?")
    except Exception as e:
        print(f"Error procesando mensaje: {e}")

    return "EVENT_RECEIVED", 200

def enviar_mensaje(number, text):
    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": number,
        "type": "text",
        "text": {"body": text}
    }
    response = requests.post(url, json=payload, headers=headers)
    print(f"Respuesta de Meta: {response.status_code} - {response.text}") # ESTO NOS DIRA EL ERROR REAL

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
