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
CV_MOCK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cv_mock.json")
TEST_QUESTION = "¿Cómo organizarías la arquitectura de un proyecto nuevo en Django y Angular?"

SYSTEM_PROMPT = """Actúas como un copiloto de entrevistas en tiempo real para un candidato.
Tu tarea es sugerir talking points que el candidato pueda decir en voz alta.

Reglas estrictas:
- Responde únicamente con 2 o 3 viñetas muy breves (Talking Points).
- No incluyas saludos, introducciones ni despedidas.
- Basa cada punto estrictamente en la información del CV en formato JSON que se te proporciona; no inventes datos.
- Resalta en negrita (**así**) las métricas y tecnologías clave mencionadas.
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
