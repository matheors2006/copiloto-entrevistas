"""LLM reasoning engine: streams interview talking points grounded in the candidate's CV."""
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

SYSTEM_PROMPT = """REGLA DE IDIOMA: Responde EXACTAMENTE en el mismo idioma en el que se te hace la pregunta. Si la pregunta es en inglés, responde en inglés. Si es en español, responde en español. Mantén la regla de contingencia: nunca digas no sé, adapta la respuesta.

Actúas como un copiloto de entrevistas en tiempo real para un candidato.
Tu tarea es sugerir talking points que el candidato pueda decir en voz alta.

Reglas estrictas:
- Responde únicamente con 2 o 3 viñetas muy breves (Talking Points).
- No incluyas saludos, introducciones ni despedidas.
- Basa cada punto estrictamente en la información del CV en formato JSON que se te proporciona; no inventes datos.
- Resalta en negrita (**así**) las métricas y tecnologías clave mencionadas.

REGLA DE CONTINGENCIA: Si la pregunta técnica es sobre una tecnología que NO está en el CV, proporciona una explicación técnica general y precisa. Si es una pregunta situacional sobre una herramienta que el candidato no conoce, adapta la respuesta basándote en metodologías o experiencias previas de su CV. Tienes estrictamente PROHIBIDO decir frases como 'No está en el CV', 'No tienes experiencia' o 'No lo sé'.
"""


def build_user_prompt(pregunta, cv_json):
    """Combine the interview question with the candidate's CV as grounding context."""
    return (
        f"Pregunta del entrevistador: {pregunta}\n\n"
        f"CV del candidato (JSON):\n{json.dumps(cv_json, ensure_ascii=False, indent=2)}"
    )


async def stream_respuesta(pregunta, cv_json):
    """Yield response tokens from Groq as they are generated, grounded in the candidate's CV."""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY no está definido en backend/.env")

    client = AsyncGroq(api_key=GROQ_API_KEY)
    stream = await client.chat.completions.create(
        model=MODEL,
        stream=True,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(pregunta, cv_json)},
        ],
    )

    async for chunk in stream:
        token = chunk.choices[0].delta.content
        if token:
            yield token


async def procesar_cv_pdf(texto_pdf):
    """Summarize raw CV text into the app's structured profile JSON and overwrite cv_mock.json."""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY no está definido en backend/.env")

    extraction_prompt = (
        "Eres un asistente que convierte el texto crudo de un CV en un perfil JSON estructurado.\n"
        "Devuelve EXCLUSIVAMENTE un objeto JSON válido con exactamente esta forma (sin texto adicional, sin markdown):\n"
        f"{json.dumps(CV_JSON_SCHEMA_EXAMPLE, ensure_ascii=False, indent=2)}\n\n"
        "Completa los valores con la información real extraída del CV. Si algún dato no aparece en el texto, "
        "infierelo de forma razonable o usa un valor vacío apropiado, pero no dejes ningún campo ausente."
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
    """Quickly translate an English question into Spanish using a smaller, faster model."""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY no está definido en backend/.env")

    client = AsyncGroq(api_key=GROQ_API_KEY)
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


async def _run_test():
    """Load the mock CV, ask the test question, and print tokens as they arrive."""
    with open(CV_MOCK_PATH, encoding="utf-8") as f:
        cv_json = json.load(f)

    print(f"Pregunta: {TEST_QUESTION}\n")
    async for token in stream_respuesta(TEST_QUESTION, cv_json):
        print(token, end="", flush=True)
    print()


if __name__ == "__main__":
    asyncio.run(_run_test())
