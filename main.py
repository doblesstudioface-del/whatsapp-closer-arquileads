from flask import Flask, request
import requests
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse

app = Flask(__name__)

ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
GRAPH_API_VERSION = os.environ.get("GRAPH_API_VERSION", "v25.0")

SHEETS_WEBHOOK_URL = os.environ.get("SHEETS_WEBHOOK_URL")
ALERT_PHONE_NUMBER = os.environ.get("ALERT_PHONE_NUMBER")

CONVERSACIONES = {}

PALABRAS_LEAD_CALIENTE = [
    "quiero", "me interesa", "revisar", "revision", "revisión", "diagnostico", "diagnóstico",
    "agendar", "llamada", "cotizar", "cotizacion", "cotización", "precio", "costo",
    "cuanto", "cuánto", "contratar", "empezar", "esta semana", "este mes", "urgente"
]

URL_REGEX = re.compile(r"https?://[^\s]+|www\.[^\s]+", re.IGNORECASE)
CTA_KEYWORDS = ["contacto", "contactar", "agenda", "agendar", "cotiza", "cotizar", "whatsapp", "llamada", "consulta", "proyecto"]
ARCHITECTURE_KEYWORDS = ["arquitectura", "arquitecto", "arquitectos", "estudio", "interiorismo", "diseño interior", "proyectos", "residencial"]


def ahora_iso():
    return datetime.utcnow().isoformat()


def normalizar_texto(texto):
    return (texto or "").strip().lower()


def extraer_url(texto):
    match = URL_REGEX.search(texto or "")
    if not match:
        return None
    url = match.group(0).strip().rstrip(".,);]")
    if url.startswith("www."):
        url = "https://" + url
    return url


def obtener_estado(number):
    if number not in CONVERSACIONES:
        CONVERSACIONES[number] = crear_estado(number)
    return CONVERSACIONES[number]


def crear_estado(number):
    return {
        "telefono": number,
        "etapa": "inicio",
        "situacion_web": None,
        "genera_contactos": None,
        "comunica_valor": None,
        "quiere_oportunidades": None,
        "problema_detectado": None,
        "presupuesto": None,
        "url_web": None,
        "diagnostico_web": None,
        "lead_caliente": False,
        "alerta_enviada": False,
        "guardado_en_sheets": False,
        "mensajes": [],
        "creado_en": ahora_iso(),
        "actualizado_en": ahora_iso(),
    }


def guardar_mensaje(number, role, text):
    estado = obtener_estado(number)
    estado["mensajes"].append({"role": role, "text": text, "timestamp": ahora_iso()})
    estado["actualizado_en"] = ahora_iso()
    estado["mensajes"] = estado["mensajes"][-20:]


def reiniciar_conversacion(number):
    CONVERSACIONES[number] = crear_estado(number)
    return CONVERSACIONES[number]


def detectar_situacion_web(texto):
    texto = normalizar_texto(texto)
    if any(p in texto for p in ["no tengo", "desde cero", "empezando", "empezar", "nueva", "crear"]):
        return "no tiene web"
    if any(p in texto for p in ["no convierte", "no genera", "no llegan", "sin contactos", "no funciona"]):
        return "tiene web pero no convierte"
    if any(p in texto for p in ["no comunica", "no se entiende", "solo visual", "portafolio", "valor"]):
        return "tiene web pero no comunica bien su valor"
    if any(p in texto for p in ["si tengo", "sí tengo", "tengo web", "ya tengo", "activa"]):
        return "tiene web activa"
    return None


def respuesta_precio():
    return (
        "Nuestros proyectos suelen empezar alrededor de $2500, dependiendo del alcance.\n\n"
        "No es solo diseño: trabajamos estructura, velocidad y mensaje para que la web realmente genere clientes.\n\n"
        "Para orientarte mejor, primero tendría que entender tu caso.\n"
        "¿Tu web actual ya está funcionando o estás empezando desde cero?"
    )


def analizar_web(url):
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ["http", "https"] or not parsed.netloc:
            return "No pude leer ese enlace. Envíame una URL completa, por ejemplo: https://tusitio.com"

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ArquileadsBot/1.0; +https://example.com/bot)"
        }
        response = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
        status = response.status_code

        if status >= 400:
            return (
                "Intenté revisar la web, pero respondió con un error.\n\n"
                f"Código detectado: {status}.\n\n"
                "Esto ya es una señal importante: si el sitio no carga de forma estable, puede afectar la confianza y la conversión."
            )

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        title = (soup.title.string.strip() if soup.title and soup.title.string else "")
        meta_description_tag = soup.find("meta", attrs={"name": "description"})
        meta_description = meta_description_tag.get("content", "").strip() if meta_description_tag else ""
        h1 = soup.find("h1")
        h1_text = h1.get_text(" ", strip=True) if h1 else ""
        body_text = soup.get_text(" ", strip=True).lower()
        links_text = " ".join(a.get_text(" ", strip=True).lower() for a in soup.find_all("a"))
        hrefs = " ".join(a.get("href", "").lower() for a in soup.find_all("a"))

        tiene_cta = any(keyword in links_text or keyword in body_text for keyword in CTA_KEYWORDS)
        tiene_whatsapp = "wa.me" in hrefs or "whatsapp" in hrefs or "whatsapp" in body_text
        parece_arquitectura = any(keyword in body_text for keyword in ARCHITECTURE_KEYWORDS)

        hallazgos = []
        mejoras = []

        if title:
            hallazgos.append("La web tiene título definido.")
        else:
            mejoras.append("Falta un título claro para la página.")

        if meta_description:
            hallazgos.append("Tiene descripción para buscadores.")
        else:
            mejoras.append("No encontré una meta descripción clara; eso puede afectar cómo se entiende la web en Google.")

        if h1_text:
            if len(h1_text) < 35:
                mejoras.append("El mensaje principal parece corto; conviene explicar mejor qué hace el estudio y para quién.")
            else:
                hallazgos.append("Tiene un mensaje principal visible.")
        else:
            mejoras.append("No encontré un H1 claro; el primer mensaje debería explicar rápido el valor del estudio.")

        if tiene_cta:
            hallazgos.append("Tiene alguna llamada a la acción.")
        else:
            mejoras.append("No detecté una llamada clara a contacto, agenda o cotización.")

        if tiene_whatsapp:
            hallazgos.append("Hay señal de contacto por WhatsApp.")
        else:
            mejoras.append("No detecté un acceso claro a WhatsApp; para conversión suele ser clave.")

        if not parece_arquitectura:
            mejoras.append("No queda suficientemente claro, desde el texto inicial, que sea una web enfocada en arquitectura/interiorismo.")

        if not mejoras:
            mejoras.append("La base parece correcta. El siguiente paso sería revisar si el mensaje realmente diferencia al estudio y guía al visitante hacia contacto.")

        diagnostico = (
            "Revisé la web de forma automática.\n\n"
            "Primer diagnóstico:\n"
            f"• {mejoras[0]}\n"
        )

        if len(mejoras) > 1:
            diagnostico += f"• {mejoras[1]}\n"
        if hallazgos:
            diagnostico += f"\nAlgo positivo: {hallazgos[0]}\n"

        diagnostico += (
            "\nMi lectura: puede haber oportunidad de mejorar claridad, estructura y conversión, no solo diseño visual.\n\n"
            "Para afinar el diagnóstico: ¿qué tipo de proyectos quiere atraer tu estudio?"
        )
        return diagnostico

    except requests.RequestException:
        return (
            "Intenté revisar la web, pero no pude cargarla correctamente.\n\n"
            "Puede ser un bloqueo del servidor, un problema temporal o una URL incompleta. Envíame el enlace completo y lo revisamos de nuevo."
        )
    except Exception as e:
        print(f"Error analizando web: {e}")
        return (
            "Pude recibir el enlace, pero no logré analizarlo con claridad.\n\n"
            "Lo mejor sería escalarlo a una revisión humana para darte un diagnóstico más preciso."
        )


def respuesta_con_memoria(number, mensaje):
    texto = normalizar_texto(mensaje)
    estado = obtener_estado(number)
    url_detectada = extraer_url(mensaje)

    if url_detectada:
        estado["url_web"] = url_detectada
        estado["lead_caliente"] = True
        estado["etapa"] = "cerrar"
        diagnostico = analizar_web(url_detectada)
        estado["diagnostico_web"] = diagnostico
        return diagnostico

    if texto in ["reiniciar", "reset", "empezar de nuevo", "inicio"]:
        reiniciar_conversacion(number)
        return (
            "Listo, empecemos de nuevo.\n\n"
            "Ayudamos a estudios de arquitectura a convertir su web en una herramienta que genere clientes.\n\n"
            "¿Tu web actual ya está funcionando o estás empezando desde cero?"
        )

    if any(p in texto for p in ["precio", "costo", "cuanto", "cuánto", "presupuesto"]):
        estado["presupuesto"] = mensaje.strip()
        estado["lead_caliente"] = True
        return respuesta_precio()

    etapa = estado.get("etapa", "inicio")

    if etapa == "inicio":
        situacion = detectar_situacion_web(texto)
        if situacion:
            estado["situacion_web"] = situacion
            estado["etapa"] = "detectar_contactos"
            return "Entiendo. ¿Esa web te está generando contactos o funciona más como portafolio?"

        estado["etapa"] = "detectar_contexto"
        return (
            "Hola. Ayudamos a estudios de arquitectura a que su web no sea solo un portafolio bonito, sino una herramienta para generar clientes.\n\n"
            "¿Tu web actual ya está funcionando o estás empezando desde cero?"
        )

    if etapa == "detectar_contexto":
        estado["situacion_web"] = detectar_situacion_web(texto) or mensaje.strip()
        estado["etapa"] = "detectar_contactos"
        return "¿Te está generando contactos o funciona más como portafolio?"

    if etapa == "detectar_contactos":
        estado["genera_contactos"] = mensaje.strip()
        estado["etapa"] = "detectar_valor"
        return "¿Sientes que comunica bien el valor del estudio o se queda más en lo visual?"

    if etapa == "detectar_valor":
        estado["comunica_valor"] = mensaje.strip()
        estado["problema_detectado"] = detectar_problema(estado)
        estado["etapa"] = "reencuadrar"
        return (
            "Tiene sentido. Muchos estudios tienen webs bien diseñadas, pero no están pensadas para convertir visitas en oportunidades reales.\n\n"
            "¿Te gustaría que tu web empezara a generar oportunidades de forma más constante?"
        )

    if etapa == "reencuadrar":
        estado["quiere_oportunidades"] = mensaje.strip()
        estado["etapa"] = "ofrecer_diagnostico"
        if respuesta_afirmativa(texto):
            estado["lead_caliente"] = True
            return (
                "Entonces hay buen punto de partida.\n\n"
                "Nosotros trabajamos justo eso: estructura, velocidad y claridad para que la web realmente apoye la captación de clientes.\n\n"
                "Envíame el link de tu web y te doy un primer diagnóstico automático."
            )
        return (
            "Perfecto. En ese caso no forzaría un proyecto todavía.\n\n"
            "Cuando quieras revisar si tu web está frenando oportunidades, puedo ayudarte con un diagnóstico breve."
        )

    if etapa == "ofrecer_diagnostico":
        if respuesta_afirmativa(texto) or any(p in texto for p in ["diagnostico", "diagnóstico", "revisar", "web", "link"]):
            estado["lead_caliente"] = True
            estado["etapa"] = "cerrar"
            return (
                "Perfecto. Envíame el link de tu web.\n\n"
                "Haré una primera revisión automática de claridad, estructura y llamadas a la acción."
            )
        return "Entendido. ¿Quieres que te explique qué revisamos normalmente en un diagnóstico web?"

    if etapa == "cerrar":
        estado["lead_caliente"] = True
        return (
            "Recibido. Para darte un diagnóstico más útil, dime también: ¿qué tipo de proyectos quiere atraer tu estudio?"
        )

    estado["etapa"] = "inicio"
    return "Volvamos al inicio: ¿tu web actual ya está funcionando o estás empezando desde cero?"


def respuesta_afirmativa(texto):
    return any(p in texto for p in ["si", "sí", "claro", "quiero", "me interesa", "ok", "dale", "por supuesto"])


def detectar_problema(estado):
    situacion = normalizar_texto(estado.get("situacion_web"))
    contactos = normalizar_texto(estado.get("genera_contactos"))
    valor = normalizar_texto(estado.get("comunica_valor"))

    if "no tiene" in situacion or "desde cero" in situacion:
        return "no tiene web"
    if any(p in contactos for p in ["no", "pocos", "nada", "portafolio", "solo"]):
        return "tiene web pero no convierte"
    if any(p in valor for p in ["no", "visual", "bonita", "confuso", "no comunica"]):
        return "tiene web pero no comunica bien su valor"
    return "requiere diagnóstico"


def es_lead_caliente(texto, estado):
    texto = normalizar_texto(texto)
    return estado.get("lead_caliente") or any(p in texto for p in PALABRAS_LEAD_CALIENTE) or estado.get("etapa") in ["ofrecer_diagnostico", "cerrar"]


def construir_payload_lead(number, estado):
    ultimo_mensaje = estado["mensajes"][-1].get("text", "") if estado.get("mensajes") else ""
    return {
        "fecha": ahora_iso(),
        "telefono": number,
        "situacion_web": estado.get("situacion_web") or "",
        "genera_contactos": estado.get("genera_contactos") or "",
        "comunica_valor": estado.get("comunica_valor") or "",
        "quiere_oportunidades": estado.get("quiere_oportunidades") or "",
        "problema_detectado": estado.get("problema_detectado") or "",
        "presupuesto": estado.get("presupuesto") or "",
        "url_web": estado.get("url_web") or "",
        "diagnostico_web": estado.get("diagnostico_web") or "",
        "etapa": estado.get("etapa") or "",
        "lead_caliente": estado.get("lead_caliente", False),
        "ultimo_mensaje": ultimo_mensaje,
        "resumen": construir_resumen_interno(estado),
    }


def construir_resumen_interno(estado):
    return (
        f"Situacion web: {estado.get('situacion_web') or 'no especificado'} | "
        f"Contactos: {estado.get('genera_contactos') or 'no especificado'} | "
        f"Valor: {estado.get('comunica_valor') or 'no especificado'} | "
        f"Problema: {estado.get('problema_detectado') or 'no especificado'} | "
        f"URL: {estado.get('url_web') or 'no especificado'} | "
        f"Etapa: {estado.get('etapa') or 'no especificado'}"
    )


def guardar_lead_en_sheets(number, estado):
    if not SHEETS_WEBHOOK_URL:
        print("SHEETS_WEBHOOK_URL no configurado. Lead no enviado a Sheets.")
        return False
    try:
        response = requests.post(SHEETS_WEBHOOK_URL, json=construir_payload_lead(number, estado), timeout=15)
        print(f"Respuesta de Google Sheets webhook: {response.status_code} - {response.text}")
        return response.status_code in [200, 201, 202]
    except requests.RequestException as e:
        print(f"Error enviando lead a Google Sheets: {e}")
        return False


def enviar_alerta_lead_caliente(number, estado):
    if not ALERT_PHONE_NUMBER or estado.get("alerta_enviada"):
        return False
    mensaje = (
        "🔥 LEAD CALIENTE - ESTUDIO DE ARQUITECTURA\n\n"
        f"Telefono: {number}\n"
        f"Situacion web: {estado.get('situacion_web') or 'no especificado'}\n"
        f"Contactos: {estado.get('genera_contactos') or 'no especificado'}\n"
        f"Valor: {estado.get('comunica_valor') or 'no especificado'}\n"
        f"Problema: {estado.get('problema_detectado') or 'no especificado'}\n"
        f"Web: {estado.get('url_web') or 'no enviada'}\n\n"
        "Recomendacion: ofrecer diagnóstico estratégico breve."
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

    datos_suficientes = estado.get("situacion_web") and estado.get("genera_contactos")
    if estado.get("lead_caliente") or datos_suficientes or estado.get("etapa") == "cerrar":
        if guardar_lead_en_sheets(number, estado):
            estado["guardado_en_sheets"] = True


@app.route("/", methods=["GET"])
def home():
    return "Asistente web para estudios de arquitectura activo", 200


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
                for message in value.get("messages", []):
                    number = message.get("from")
                    message_type = message.get("type")
                    if not number:
                        continue
                    if message_type != "text":
                        respuesta = "Gracias. Por ahora puedo responder mejor si me escribes en texto. ¿Tu web ya está funcionando o empiezas desde cero?"
                        guardar_mensaje(number, "assistant", respuesta)
                        enviar_mensaje(number, respuesta)
                        continue

                    message_body = message.get("text", {}).get("body", "")
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
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": number, "type": "text", "text": {"body": text}}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        print(f"Respuesta de Meta: {response.status_code} - {response.text}")
        return 200 <= response.status_code < 300
    except requests.RequestException as e:
        print(f"Error enviando mensaje a Meta: {e}")
        return False


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
