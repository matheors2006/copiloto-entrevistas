"""LLM reasoning engine: streams interview talking points grounded in the candidate's CV or General Knowledge."""
import asyncio
import json
import os
import sys

from groq import AsyncGroq
from dotenv import load_dotenv

if sys.platform == "win32":
    os.system("chcp 65001 >nul")

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "openai/gpt-oss-120b"
FAST_MODEL = "openai/gpt-oss-20b"
CV_MOCK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cv_mock.json")
TEST_QUESTION = "¿Cómo organizarías la arquitectura de un proyecto nuevo en Django y Angular?"

CV_JSON_SCHEMA_EXAMPLE = {
    "full_name": "string",
    "role": "string",
    "age": 0,
    "years_of_experience": 0,
    "summary": "string",
    "core_skills": ["string"],
    "key_competencies": [{"name": "string", "description": "string"}],
    "notable_project": {
        "name": "string",
        "description": "string",
        "technologies": ["string"],
        "impact": "string",
    },
    "education": {"degree": "string", "status": "string"},
}

# --- PROMPT PARA MODO CV ---
SYSTEM_PROMPT = """REGLA DE IDIOMA: Responde EXACTAMENTE en el mismo idioma en el que se te hace la pregunta. Si la pregunta es en inglés, responde en inglés. Si es en español, responde en español. Mantén la regla de contingencia: nunca digas no sé, adapta la respuesta.

INSTRUCCIÓN CRÍTICA: Debes detectar en qué idioma está escrita la pregunta del usuario. Si la pregunta está en INGLÉS, tu respuesta completa DEBE ser en INGLÉS. Si está en ESPAÑOL, responde en ESPAÑOL.

PERSONA: Eres el candidato en una entrevista técnica, un desarrollador humano real. NO eres un asistente de inteligencia artificial y jamás debes sonar como uno. Responde siempre en primera persona del singular o plural ("yo construí", "nosotros implementamos", "mi enfoque es"), como si el CV en JSON que se te proporciona fuera tu propia experiencia.

TONO: Habla de tú a tú con el entrevistador, como ingeniero a ingeniero. Usa un tono natural, relajado pero profesional, como si estuvieras tomando un café mientras explicas arquitectura. Abre tus ideas con conectores orgánicos: en español usa frases como "Bueno, en ese caso...", "Lo principal aquí sería...", "La verdad es que prefiero...", "Mira, normalmente lo que hago es..."; en inglés usa sus equivalentes naturales como "Well, in that case...", "The main thing here would be...", "Honestly, I prefer...", "So, what I usually do is...". El idioma de la REGLA DE IDIOMA y del mensaje de idioma detectado SIEMPRE tiene prioridad sobre estos ejemplos.

FORMATO ESTRICTAMENTE PROHIBIDO: Tienes PROHIBIDO usar listas numeradas robóticas (1., 2., 3.), estructuras de tutorial ("Paso 1", "Paso 2") o frases cliché de IA ("Aquí tienes cómo lo haría", "En resumen", "En conclusión"). No des respuestas exhaustivas de manual. Ve directo al grano, con respuestas concisas.

RESPUESTAS SITUACIONALES: Si te plantean un problema hipotético, no des un plan de acción de 10 pasos. Responde como alguien que razona en voz alta. Ejemplo del tono deseado: "Lo primero que revisaría son los logs para aislar el error. Si el problema viene de la base de datos, probablemente implementaría un sistema de caché con Redis para liberar carga, algo parecido a lo que hicimos en ENAPRES...".

FORMATO VISUAL: Genera talking points (ideas clave cortas) separadas por un salto de línea, sin numerarlas ni usar viñetas con guiones. Deben ser bloques de texto cortos que el candidato pueda leer de reojo y decir en voz alta con fluidez.

Basa cada punto estrictamente en la información del CV en formato JSON que se te proporciona; no inventes datos. Resalta en negrita (**así**) las métricas y tecnologías clave mencionadas.

REGLA DE CONTINGENCIA: Si la pregunta técnica es sobre una tecnología que NO está en el CV, proporciona una explicación técnica general y precisa. Tienes estrictamente PROHIBIDO decir frases como 'No está en el CV', 'No tienes experiencia' o 'No lo sé'.
"""

# --- PROMPT PARA MODO GENERAL (IA/SENIOR) ---
SYSTEM_PROMPT_GENERAL = """REGLA ABSOLUTA Y SUPREMA: Eres un desarrollador humano real, un Arquitecto de Software Senior en medio de una charla técnica. NO eres un asistente de inteligencia artificial. Responde siempre en primera persona del singular o plural.

INSTRUCCIÓN CRÍTICA: Debes detectar en qué idioma está escrita la pregunta del usuario. Si la pregunta está en INGLÉS, tu respuesta completa DEBE ser en INGLÉS. Si está en ESPAÑOL, responde en ESPAÑOL.

TONO CONVERSACIONAL: Habla de tú a tú con el entrevistador, como ingeniero a ingeniero. Usa un tono natural, relajado pero magistral. Imagina que estás tomando un café mientras explicas arquitectura. Usa conectores orgánicos al inicio de tus ideas (ejemplo: 'Bueno, la forma en la que yo lo veo...', 'Lo principal aquí sería...', 'La verdad es que prefiero...'). 

FORMATO ESTRICTAMENTE PROHIBIDO: TIENES PROHIBIDO usar listas numeradas robóticas (1., 2., 3.), estructuras de tutorial ('Paso 1', 'Paso 2') o frases cliché de IA ('Aquí tienes la explicación', 'En resumen', 'Espero que esto te sirva'). Ve directo al grano, como un humano que razona en voz alta.

CONOCIMIENTO TÉCNICO GENERAL: El entrevistador te hará una pregunta técnica (ej. '¿Para qué sirve AWS Lambda?'). Responde demostrando un conocimiento profundo, teórico y práctico, pero con palabras tuyas y ejemplos del mundo real. No dependes de un CV, usa toda tu maestría técnica libremente.

FORMATO VISUAL: Genera Talking Points (ideas clave cortas) separadas por un salto de línea, sin numerar y sin guiones. Deben ser bloques de texto cortos que el usuario pueda leer de reojo y hablar fluidamente sin parecer que lee un guion. Resalta en negrita (**así**) los conceptos técnicos clave.
"""


def build_user_prompt(pregunta, cv_json):
    """Combine the interview question with the candidate's CV as grounding context."""
    return (
        f"Pregunta del entrevistador: {pregunta}\n\n"
        f"CV del candidato (JSON):\n{json.dumps(cv_json, ensure_ascii=False, indent=2)}"
    )


def build_language_lock_prompt(idioma_detectado):
    return (
        f"¡IMPORTANTE! El entrevistador ha hablado en código de idioma '{idioma_detectado}'. "
        "DEBES redactar tu respuesta ÚNICA Y ESTRICTAMENTE en ese idioma. "
        "Si es 'en', responde en Inglés. Si es 'es', responde en Español. "
        "Esta instrucción de idioma tiene prioridad absoluta."
    )


async def stream_respuesta(pregunta, cv_json, idioma_detectado="es", modo="cv"):
    """Yield response tokens from Groq as they are generated.
    Switches behavior based on 'modo' ('cv' or 'general').
    """
    if not GROQ_API_KEY:
        print("Error en stream_respuesta: GROQ_API_KEY no está definido en backend/.env")
        return

    client = AsyncGroq(api_key=GROQ_API_KEY)
    
    # Decidir qué Prompt y Contexto enviar según el modo seleccionado
    if modo == "general":
        sys_prompt_activo = SYSTEM_PROMPT_GENERAL
        user_prompt_activo = f"Pregunta del entrevistador: {pregunta}"
    else:
        sys_prompt_activo = SYSTEM_PROMPT
        user_prompt_activo = build_user_prompt(pregunta, cv_json)

    try:
        stream = await client.chat.completions.create(
            model=MODEL,
            stream=True,
            messages=[
                {"role": "system", "content": sys_prompt_activo},
                {"role": "user", "content": user_prompt_activo},
                {"role": "system", "content": build_language_lock_prompt(idioma_detectado)},
            ],
        )

        async for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                yield token
    except Exception as error:
        print(f"Error en stream_respuesta: {error}")


async def procesar_cv_pdf(texto_pdf):
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY no está definido en backend/.env")

    extraction_prompt = (
        "Eres un asistente que convierte el texto crudo de un CV en un perfil JSON estructurado.\n"
        "Devuelve EXCLUSIVAMENTE un objeto JSON válido con exactamente esta forma:\n"
        f"{json.dumps(CV_JSON_SCHEMA_EXAMPLE, ensure_ascii=False, indent=2)}\n\n"
        "Completa los valores con la información real extraída del CV. Infierelo de forma razonable si falta."
    )

    client = AsyncGroq(api_key=GROQ_API_KEY)
    response = await client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": extraction_prompt},
            {"role": "user", "content": texto_pdf},
        ],
    )

    nuevo_cv_json = json.loads(response.choices[0].message.content)
    with open(CV_MOCK_PATH, "w", encoding="utf-8") as f:
        json.dump(nuevo_cv_json, f, ensure_ascii=False, indent=2)

    return nuevo_cv_json


async def traducir_pregunta(pregunta_ingles):
    if not GROQ_API_KEY:
        print("Error en traducir_pregunta: GROQ_API_KEY no está definido en backend/.env")
        return None

    client = AsyncGroq(api_key=GROQ_API_KEY)
    try:
        response = await client.chat.completions.create(
            model=FAST_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Traduce el siguiente texto al español. Responde únicamente con la traducción, sin explicaciones ni comillas.",
                },
                {"role": "user", "content": pregunta_ingles},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as error:
        print(f"Error en traducir_pregunta: {error}")
        return None


async def _run_test():
    with open(CV_MOCK_PATH, encoding="utf-8") as f:
        cv_json = json.load(f)

    print(f"Pregunta: {TEST_QUESTION}\n")
    # Prueba del modo CV
    print("--- MODO CV ---")
    async for token in stream_respuesta(TEST_QUESTION, cv_json, modo="cv"):
        print(token, end="", flush=True)
    print("\n")
    
    # Prueba del modo General
    print("--- MODO GENERAL ---")
    async for token in stream_respuesta(TEST_QUESTION, cv_json, modo="general"):
        print(token, end="", flush=True)
    print()

if __name__ == "__main__":
    asyncio.run(_run_test())