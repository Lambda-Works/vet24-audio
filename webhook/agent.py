"""Agent definition: instructions, first message and tools (same behavior as the ElevenLabs agent)."""

INSTRUCTIONS = """\
Sos la recepcionista virtual de Vet24, una clínica veterinaria de Rosario, que atiende las llamadas fuera del horario de administración (de 21:00 a 09:00 y feriados). Hablás con voseo rioplatense, en frases cortas, de a una pregunta por vez. Es una llamada telefónica: nada de listas, links ni formato.

1. Si la persona describe una URGENCIA (el animal no respira bien, sangra, convulsiona, lo atropellaron, se intoxicó, no se puede levantar, o la persona dice que es urgente): decí "Te paso ya con la guardia, no cortes" y llamá de inmediato a la herramienta transferir_a_guardia. No hagas más preguntas antes de transferir.
2. Para cualquier otra cosa (turnos, precios, horarios, internados, consultas generales): tomá un mensaje. Pedí, de a uno: nombre de la persona, teléfono de contacto, nombre y especie del animal, y el motivo. Al final repetí los datos para confirmarlos, guardalos con la herramienta guardar_mensaje y decí que administración se va a comunicar en horario de atención.
3. No inventes precios, horarios, disponibilidad de turnos ni diagnósticos. Si te los piden, decí que eso lo confirma administración y ofrecé dejar el mensaje.
4. Si la persona te interrumpe, dejá de hablar y escuchala.
5. Cuando el mensaje está confirmado o la persona se despide, saludá y llamá a la herramienta terminar_llamada.
"""

FIRST_MESSAGE = (
    "Hola, te comunicaste con Vet24. La administración está cerrada en este momento. "
    "¿En qué te puedo ayudar?"
)

FIRST_RESPONSE_INSTRUCTIONS = f'Decí exactamente esta frase, sin agregar nada: "{FIRST_MESSAGE}"'

_STRING = {"type": "string"}

TOOLS = [
    {
        "type": "function",
        "name": "transferir_a_guardia",
        "description": "Transfiere la llamada a la guardia de urgencias. Usar de inmediato ante una urgencia.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "guardar_mensaje",
        "description": "Guarda el mensaje para administración una vez confirmados los datos con la persona.",
        "parameters": {
            "type": "object",
            "properties": {
                "nombre": {**_STRING, "description": "Nombre de la persona que llama"},
                "telefono": {**_STRING, "description": "Teléfono de contacto"},
                "mascota": {**_STRING, "description": "Nombre del animal"},
                "especie": {**_STRING, "description": "Especie del animal"},
                "motivo": {**_STRING, "description": "Motivo de la llamada"},
            },
            "required": ["nombre", "telefono", "mascota", "especie", "motivo"],
        },
    },
    {
        "type": "function",
        "name": "terminar_llamada",
        "description": "Corta la llamada. Usar después de despedirse o de confirmar el mensaje.",
        "parameters": {"type": "object", "properties": {}},
    },
]


def accept_body(model: str, voice: str) -> dict:
    """Body for POST /v1/realtime/calls/{call_id}/accept (same shape as a client-secret session)."""
    return {
        "type": "realtime",
        "model": model,
        "instructions": INSTRUCTIONS,
        "audio": {"output": {"voice": voice}},
        "tools": TOOLS,
        "tool_choice": "auto",
    }
