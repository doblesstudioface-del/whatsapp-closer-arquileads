from flask import Flask, request
import requests
import os
from datetime import datetime

app = Flask(__name__)

ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
GRAPH_API_VERSION = os.environ.get("GRAPH_API_VERSION", "v25.0")

# Opcionales para CRM y alertas
SHEETS_WEBHOOK_URL = os.environ.get("SHEETS_WEBHOOK_URL")
ALERT_PHONE_NUMBER = os.environ.get("ALERT_PHONE_NUMBER")

# Memoria temporal por numero de WhatsApp.
# Importante: en Render esta memoria se puede perder si el servicio reinicia.
# Google Sheets funcionara como registro externo de leads.
CONVERSACIONES = {}

PALABRAS_LEAD_CALIENTE = [
    "quiero", "me interesa", "agendar", "llamada", "cotizar", "cotizacion", "cotización",
    "precio", "costo", "cuanto", "cuánto", "hoy", "esta semana", "urgente", "contratar",
    "empezar", "pagar", "presupuesto"
]


def ahora_iso():
    return datetime.utcnow().isoformat()


def normalizar_texto(texto):
    return (texto or "").strip().lower()


def obtener_estado(number):
    if number not in CONVERSACIONES:
        CONVERSACIONES[number] = {
            "telefono": number,
            "etapa": "inicio",
            "servicio": None,
            "negocio": None,
            "web_actual": None,
            "presupuesto": None,
            "urgencia": None,
            "lead_caliente": False,
            "alerta_enviada": False,
            "guardado_en_sheets": False,
            "mensajes": [],
            "creado_en": ahora_iso(),
            "actualizado_en": ahora_iso(),
        }
    return CONVERSACIONES[number]


def guardar_mensaje(number, role, text):
    estado = obtener_estado(number)
    estado["mensajes"].append({
        "role": role,
        "text": text,
        "timestamp": ahora_iso(),
    })
    estado["actualizado_en"] = ahora_iso()
    estado["mensajes"] = estado["mensajes"][-20:]


def reiniciar_conversacion(number):
    CONVERSACIONES[number] = {
        "telefono": number,
        "etapa": "inicio",
        "servicio": None,
        "negocio": None,
        "web_actual": None,
        "presupuesto": None,
        "urgencia": None,
        "lead_caliente": False,
        "alerta_enviada": False,
        "guardado_en_sheets": False,
        "mensajes": [],
        "creado_en": ahora_iso(),
        "actualizado_en": ahora_iso(),
    }
    return CONVERSACIONES[number]


def detectar_servicio(texto):
    if any(p in texto for p in ["landing", "pagina", "página", "web", "sitio"]):
        return "landing page"
    if any(p in texto for p in ["whatsapp", "bot", "automatizar", "automatico", "automático", "responder"]):
        return "automatización de WhatsApp"
    if any(p in texto for p in ["clientes", "leads", "ventas", "marketing"]):
        return "captación de leads"
    if texto in ["1", "uno"]:
        return "landing page"
    if texto in ["2", "dos"]:
        return "automatización de WhatsApp"
    if texto in ["3", "tres"]:
        return "captación de leads"
    return None


def es_lead_caliente(texto, estado):
    texto = normalizar_texto(texto)
    tiene_palabra_caliente = any(p in texto for p in PALABRAS_LEAD_CALIENTE)
    etapa_avanzada = estado.get("etapa") in ["preguntar_urgencia", "cerrar"]
    urgencia = normalizar_texto(estado.get("urgencia") or "")
    urgencia_alta = any(p in urgencia for p in ["1", "esta semana", "hoy", "urgente", "ya"])
    return tiene_palabra_caliente or etapa_avanzada or urgencia_alta


def construir_payload_lead(number, estado):
    ultimo_mensaje = ""
    if estado.get("mensajes"):
        ultimo_mensaje = estado["mensajes"][-1].get("text", "")

    return {
        "fecha": ahora_iso(),
        "telefono": number,
        "servicio": estado.get("servicio") or "",
        "negocio": estado.get("negocio") or "",
        "web_actual": estado.get("web_actual") or "",
        "presupuesto": estado.get("presupuesto") or "",
        "urgencia": estado.get("urgencia") or "",
        "etapa": estado.get("etapa") or "",
        "lead_caliente": estado.get("lead_caliente", False),
        "ultimo_mensaje": ultimo_mensaje,
        "resumen": construir_resumen_interno(estado),
    }


def construir_resumen_interno(estado):
    return (
        f"Servicio: {estado.get('servicio') or 'no especificado'} | "
        f"Negocio: {estado.get('negocio') or 'no especificado'} | "
        f"Web: {estado.get('web_actual') or 'no especificado'} | "
        f"Presupuesto: {estado.get('presupuesto') or 'no especificado'} | "
        f"Urgencia: {estado.get('urgencia') or 'no especificado'} | "
        f"Etapa: {estado.get('etapa') or 'no especificado'}"
    )


def guardar_lead_en_sheets(number, estado):
    if not SHEETS_WEBHOOK_URL:
        print("SHEETS_WEBHOOK_URL no configurado. Lead no enviado a Sheets.")
        return False

    payload = construir_payload_lead(number, estado)

    try:
        response = requests.post(SHEETS_WEBHOOK_URL, json=payload, timeout=15)
        print(f"Respuesta de Google Sheets webhook: {response.status_code} - {response.text}")
        return response.status_code in [200, 201, 202]
    except requests.RequestException as e:
        print(f"Error enviando lead a Google Sheets: {e}")
        return False


def enviar_alerta_lead_caliente(number, estado):
    if not ALERT_PHONE_NUMBER:
        print("ALERT_PHONE_NUMBER no configurado. Alerta no enviada.")
        return False

    if estado.get("alerta_enviada"):
        return False

    mensaje = (
        "🔥 LEAD CALIENTE ARQUILEADS\n\n"
        f"Telefono: {number}\n"
        f"Servicio: {estado.get('servicio') or 'no especificado'}\n"
        f"Negocio: {estado.get('negocio') or 'no especificado'}\n"
        f"Web: {estado.get('web_actual') or 'no especificado'}\n"
        f"Presupuesto: {estado.get('presupuesto') or 'no especificado'}\n"
        f"Urgencia: {estado.get('urgencia') or 'no especificado'}\n\n"
        "Recomendacion: responder manualmente lo antes posible."
    )

    enviado = enviar_mensaje(ALERT_PHONE_NUMBER, mensaje)
    if enviado:
        estado["alerta_enviada"] = True
    return enviado


def procesar_crm_y_alertas(number, mensaje):
    estado = obtener_estado(number)

    if es_lead_caliente(mensaje, estado):
        estado["lead_caliente"] = True
        enviar_alerta_lead_caliente(number, estado)

    # Guarda en Sheets cuando el lead ya tiene datos suficientes o se vuelve caliente.
    datos_suficientes = estado.get("servicio") and estado.get("negocio")
    if estado.get("lead_caliente") or datos_suficientes or estado.get("etapa") == "cerrar":
        guardado = guardar_lead_en_sheets(number, estado)
        if guardado:
            estado["guardado_en_sheets"] = True


def respuesta_con_memoria(number, mensaje):
    texto = normalizar_texto(mensaje)
    estado = obtener_estado(number)

    if texto in ["reiniciar", "reset", "empezar de nuevo", "inicio"]:
        reiniciar_conversacion(number)
        return (
            "Listo, empecemos de nuevo. 👋\n\n"
            "Soy el asistente de Arquileads. ¿Qué necesitas?\n\n"
            "1. Crear una landing page premium\n"
            "2. Automatizar respuestas de WhatsApp\n"
            "3. Captar más clientes para arquitectura/interiores"
        )

    etapa = estado.get("etapa", "inicio")

    if etapa == "inicio":
        servicio = detectar_servicio(texto)
        if servicio:
            estado["servicio"] = servicio
            estado["etapa"] = "preguntar_negocio"
            return (
                f"Perfecto, te interesa {servicio}.\n\n"
                "Para recomendarte bien, dime: ¿tu negocio es de arquitectura, interiores, bienes raíces u otro rubro?"
            )

        return (
            "¡Hola! Soy el asistente de Arquileads. 👋\n\n"
            "Te puedo ayudar con:\n"
            "1. Crear una landing page premium\n"
            "2. Automatizar respuestas de WhatsApp\n"
            "3. Captar más clientes para arquitectura/interiores\n\n"
            "Respóndeme con el número o cuéntame qué necesitas."
        )

    if etapa == "preguntar_negocio":
        estado["negocio"] = mensaje.strip()
        estado["etapa"] = "preguntar_web"
        return (
            f"Excelente. Entonces trabajamos para: {estado['negocio']}.\n\n"
            "Ahora dime: ¿ya tienes página web/landing o estás empezando desde cero?"
        )

    if etapa == "preguntar_web":
        estado["web_actual"] = mensaje.strip()
        estado["etapa"] = "preguntar_presupuesto"
        return (
            "Perfecto, entendido.\n\n"
            "Para ubicarte en el paquete correcto: ¿tienes un presupuesto aproximado o prefieres que te recomiende una opción inicial?"
        )

    if etapa == "preguntar_presupuesto":
        estado["presupuesto"] = mensaje.strip()
        estado["etapa"] = "preguntar_urgencia"
        return (
            "Bien. Última pregunta para calificar el proyecto:\n\n"
            "¿Qué tan pronto quieres lanzarlo?\n"
            "1. Esta semana\n"
            "2. Este mes\n"
            "3. Solo estoy cotizando"
        )

    if etapa == "preguntar_urgencia":
        estado["urgencia"] = mensaje.strip()
        estado["etapa"] = "cerrar"
        return construir_cierre(estado)

    if etapa == "cerrar":
        if any(p in texto for p in ["si", "sí", "ok", "dale", "llamada", "agendar", "agenda", "quiero"]):
            estado["lead_caliente"] = True
            return (
                "Perfecto. Para agendar o avanzar, envíame estos datos:\n\n"
                "1. Tu nombre\n"
                "2. Nombre del negocio\n"
                "3. Mejor horario para hablar\n\n"
                "Con eso un asesor de Arquileads puede darte el siguiente paso."
            )

        if any(p in texto for p in ["precio", "costo", "cuanto", "cuánto"]):
            estado["lead_caliente"] = True
            return construir_cierre(estado)

        return (
            "Ya tengo el contexto de tu proyecto.\n\n"
            "¿Quieres que te prepare una recomendación para avanzar o prefieres agendar una llamada?"
        )

    estado["etapa"] = "inicio"
    return (
        "Volvamos al inicio. ¿Qué necesitas?\n\n"
        "1. Landing page\n"
        "2. Automatización de WhatsApp\n"
        "3. Captar más clientes"
    )


def construir_cierre(estado):
    servicio = estado.get("servicio") or "solución digital"
    negocio = estado.get("negocio") or "tu negocio"
    web_actual = estado.get("web_actual") or "no especificado"
    presupuesto = estado.get("presupuesto") or "no especificado"
    urgencia = estado.get("urgencia") or "no especificado"

    return (
        "Gracias. Con lo que me contaste, este sería el resumen:\n\n"
        f"• Servicio: {servicio}\n"
        f"• Negocio: {negocio}\n"
        f"• Situación web: {web_actual}\n"
        f"• Presupuesto: {presupuesto}\n"
        f"• Urgencia: {urgencia}\n\n"
        "Mi recomendación: empezar con una solución enfocada en captar leads y llevarlos a WhatsApp con una conversación clara.\n\n"
        "¿Quieres que te ayudemos a convertir esto en una propuesta o prefieres agendar una llamada?"
    )


@app.route("/", methods=["GET"])
def home():
    return "Arquileads WhatsApp closer con CRM y alertas activo", 200


@app.route("/memoria", methods=["GET"])
def ver_memoria():
    return CONVERSACIONES, 200


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if token == VERIFY_TOKEN:
            return challenge or "", 200

        return "Error de verificacion", 403

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
                        respuesta = "Gracias por tu mensaje. Por ahora puedo responder mejor si me escribes en texto. ¿Qué necesitas lograr con Arquileads?"
                        guardar_mensaje(number, "assistant", respuesta)
                        enviar_mensaje(number, respuesta)
                        continue

                    message_body = message.get("text", {}).get("body", "")
                    print(f"Mensaje recibido de {number}: {message_body}")

                    guardar_mensaje(number, "user", message_body)
                    respuesta = respuesta_con_memoria(number, message_body)
                    guardar_mensaje(number, "assistant", respuesta)
                    enviar_mensaje(number, respuesta)

                    procesar_crm_y_alertas(number, message_body)
                    print(f"Estado actualizado para {number}: {CONVERSACIONES.get(number)}")

    except Exception as e:
        print(f"Error procesando webhook: {e}")

    return "EVENT_RECEIVED", 200


def enviar_mensaje(number, text):
    if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
        print("Faltan ACCESS_TOKEN o PHONE_NUMBER_ID en variables de entorno")
        return False

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
        return 200 <= response.status_code < 300
    except requests.RequestException as e:
        print(f"Error enviando mensaje a Meta: {e}")
        return False


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
