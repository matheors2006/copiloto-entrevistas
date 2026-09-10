"""Generates technical summary reports in PDF and Word formats from Markdown-like plain text."""
import os
import re

from docx import Document
from fpdf import FPDF

BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")


def _iter_inline_runs(line):
    """Split a line into (text, is_bold) runs based on **bold** markers."""
    position = 0
    for match in BOLD_PATTERN.finditer(line):
        if match.start() > position:
            yield line[position:match.start()], False
        yield match.group(1), True
        position = match.end()
    if position < len(line):
        yield line[position:], False


def _to_latin1(text):
    """Sanitize text for the PDF core font, which only supports the latin-1 charset."""
    return text.encode("latin-1", "replace").decode("latin-1")


def _build_docx(title, content, output_path):
    """Render the report as a .docx file."""
    document = Document()
    document.add_heading(title, level=0)

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("## "):
            document.add_heading(line[3:], level=2)
            continue
        if line.startswith("# "):
            document.add_heading(line[2:], level=1)
            continue

        is_bullet = line.startswith("- ")
        text = line[2:] if is_bullet else line
        paragraph = document.add_paragraph(style="List Bullet" if is_bullet else None)
        for run_text, is_bold in _iter_inline_runs(text):
            run = paragraph.add_run(run_text)
            run.bold = is_bold

    document.save(output_path)


def _build_pdf(title, content, output_path):
    """Render the report as a .pdf file."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", style="B", size=16)
    pdf.multi_cell(0, 10, _to_latin1(title))
    pdf.ln(4)

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        if not line:
            pdf.ln(4)
            continue
        if line.startswith("## "):
            pdf.set_font("Helvetica", style="B", size=13)
            pdf.multi_cell(0, 9, _to_latin1(line[3:]))
            continue
        if line.startswith("# "):
            pdf.set_font("Helvetica", style="B", size=15)
            pdf.multi_cell(0, 9, _to_latin1(line[2:]))
            continue

        is_bullet = line.startswith("- ")
        text = line[2:] if is_bullet else line
        pdf.set_font("Helvetica", size=11)
        if is_bullet:
            pdf.write(7, "- ")
        for run_text, is_bold in _iter_inline_runs(text):
            pdf.set_font("Helvetica", style="B" if is_bold else "", size=11)
            pdf.write(7, _to_latin1(run_text))
        pdf.ln(9)

    pdf.output(output_path)


def generate_report(title, content, output_dir="."):
    """Export a technical summary as Reporte_Copiloto.pdf and Reporte_Copiloto.docx in output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    pdf_path = os.path.join(output_dir, "Reporte_Copiloto.pdf")
    docx_path = os.path.join(output_dir, "Reporte_Copiloto.docx")

    _build_docx(title, content, docx_path)
    _build_pdf(title, content, pdf_path)

    return pdf_path, docx_path


REPORT_TITLE = "Reporte de Arquitectura Completa - Copiloto de Entrevistas (Fases 1-6)"

REPORT_CONTENT = """
# Resumen ejecutivo

Este reporte documenta el estado completo del Copiloto de Entrevistas al cierre de la Fase 6: captura de audio del sistema, transcripcion en tiempo real con streaming de la pregunta en vivo, un motor de razonamiento LLM no bloqueante con soporte de interrupciones, el servidor FastAPI que orquesta todo el flujo, el overlay de escritorio en Tauri/React, y las nuevas capacidades de carga dinamica de CV, soporte bilingue y traduccion en vivo.

# Fase 1: Captura de audio del sistema (soundcard y Loopback)

- **soundcard** es la libreria que permite acceder a los dispositivos de audio del sistema operativo desde Python, tanto para grabar microfonos normales como para hacer **loopback**.
- El **loopback** es la tecnica que permite capturar el audio que el sistema esta reproduciendo hacia los parlantes o audifonos (por ejemplo, la voz del entrevistador en una llamada de Zoom o Meet), en lugar de depender de un microfono fisico. Esto es posible gracias a **WASAPI** (Windows Audio Session API), que expone el dispositivo de salida por defecto como si fuera un microfono de solo lectura.
- Se eligio capturar en **bloques pequenos (1024 frames)** en lugar de grabaciones largas de una sola vez, porque los bloques grandes generaban advertencias de **data discontinuity** (perdida de continuidad del buffer). Con bloques pequenos, el audio fluye de forma constante y de baja latencia, sin cortes.
- Cada bloque de audio llega como un arreglo de numeros en punto flotante (**float32**, rango -1.0 a 1.0). Antes de enviarlo a cualquier servicio externo se recorta (**clip**) a ese rango y se convierte a **PCM de 16 bits (int16)**, que es el formato que Deepgram espera recibir.

# Fase 2: Transcripcion en tiempo real con Deepgram (WebSockets)

- El audio no se envia como un archivo completo al final: se transmite **en vivo, bloque por bloque, a traves de un WebSocket** hacia los servidores de Deepgram. Un WebSocket mantiene una conexion abierta y bidireccional, ideal para audio continuo, a diferencia de una peticion HTTP tradicional que tendria que esperar a que termine la grabacion.
- Se usa el modelo **nova-2** de Deepgram, configurado con **encoding="linear16"**, **sample_rate=16000** y **channels=1**, exactamente los mismos parametros con los que se captura y convierte el audio en la Fase 1.
- El parametro **endpointing** paso por varios ajustes en pruebas reales: empezo en 900 ms, subio a 3000 ms para dar mas respiro al entrevistador, y se afino en **1500 ms** como punto medio entre una conversacion fluida y evitar cortes prematuros de la pregunta.
- Como la captura de audio (soundcard) es una operacion bloqueante y el resto del sistema es asincrono (asyncio), cada bloque se graba dentro de un hilo separado usando **asyncio.to_thread**. Esto evita que el **event loop** se congele mientras se espera el audio, permitiendo que la recepcion de transcripciones ocurra en paralelo sin bloqueos.
- **Streaming de la pregunta en vivo**: Deepgram distingue entre **is_final** (un fragmento de texto ya no cambiara) y **speech_final** (el entrevistador realmente termino de hablar, tras el silencio configurado en endpointing). El sistema acumula cada fragmento **is_final** en una variable y lo reenvia de inmediato al frontend como **{"type": "interim_question"}**, para que el usuario vea la pregunta "escribiendose" en tiempo real. Solo cuando llega **speech_final=True** se considera la pregunta completa, se envia como **{"type": "question"}** y se limpia el acumulador para la siguiente.

# Fase 3: Motor de razonamiento LLM con Groq

- **Groq** es el proveedor que ejecuta el modelo de lenguaje (LLM) a muy baja latencia. El motor implementado en **llm_engine.py** define la funcion asincrona **stream_respuesta(pregunta, cv_json)**, que envia la pregunta transcrita junto con el CV del candidato (en formato JSON) a Groq.
- El modelo configurado actualmente es **openai/gpt-oss-120b**. Originalmente se planeo usar **llama-3.3-70b-versatile**, pero al probarlo en vivo la API respondio con un error 404 (modelo no disponible para esta cuenta), por lo que se verificaron los modelos realmente disponibles y se selecciono el de mayor capacidad entre ellos.
- El **System Prompt** obliga al modelo a responder como un copiloto de entrevistas: maximo 2 o 3 viñetas muy breves (**Talking Points**), sin saludos, basadas estrictamente en el CV, con metricas y tecnologias resaltadas en negrita.
- Se agrego una **regla de contingencia**: si la pregunta es sobre una tecnologia que no aparece en el CV, el modelo debe dar una explicacion tecnica general y precisa, o adaptar la respuesta usando metodologias similares del CV, y tiene prohibido decir frases como "no esta en el CV" o "no lo se". Esto evita que el copiloto deje al candidato sin respuesta en medio de una entrevista real.
- La respuesta se genera con **stream=True**, es decir, Groq envia el texto **token por token** a medida que se genera, en lugar de esperar la respuesta completa. Esto permite mostrar la respuesta en pantalla casi de inmediato.

# Fase 4: FastAPI como orquestador central

- **main.py** expone un servidor **FastAPI** con un unico endpoint WebSocket en **/ws**. Cuando un cliente (la app de escritorio en Tauri) se conecta, el servidor acepta la conexion y arranca todo el pipeline para esa sesion.
- Al aceptar la conexion, el servidor: (1) carga el CV actualizado desde disco, (2) abre su propia conexion WebSocket hacia Deepgram, y (3) lanza en paralelo la captura de audio del sistema y el envio continuo hacia Deepgram.
- FastAPI actua como el **orquestador**: coordina tres sistemas externos (el microfono via soundcard, Deepgram para voz-a-texto, y Groq para el razonamiento) sin que ninguno bloquee a los demas, usando tareas asincronas (**asyncio.create_task**) que corren de forma concurrente.
- Cuando el cliente se desconecta, el servidor detecta el cierre mediante una tarea que escucha la desconexion (**websocket.receive_text**), y cancela de forma ordenada todas las tareas en segundo plano, evitando procesos huerfanos.
- **Correccion critica de concurrencia**: en pruebas reales, el sistema se congelaba a partir de la tercera pregunta. La causa era que el SDK de Deepgram espera (**await**) a que termine cada callback antes de leer el siguiente mensaje del WebSocket; como el callback hacia **await** directo sobre todo el streaming de **stream_respuesta**, el listener de Deepgram quedaba bloqueado mientras el LLM respondia. La solucion fue desacoplar el LLM en una tarea independiente (**llm_task = asyncio.create_task(...)**) en lugar de esperarla directamente, permitiendo que el listener siga procesando mensajes de inmediato.
- **Soporte de interrupciones**: si el entrevistador hace una nueva pregunta mientras el LLM todavia esta respondiendo la anterior, el sistema cancela la tarea vieja (**llm_task.cancel()**) antes de lanzar una nueva, y envia un evento **{"type": "clear_answer"}** para que la interfaz limpie la respuesta anterior de inmediato.

# Fase 5: Overlay de escritorio con Tauri y React

- El frontend es una aplicacion **Tauri** (Rust + WebView) con interfaz en **React y TypeScript**, estilizada con **TailwindCSS**. Se eligio Tauri en lugar de Electron por su menor consumo de recursos y por generar un binario nativo mas liviano.
- La ventana esta configurada como un **overlay flotante**: siempre encima de otras ventanas (**alwaysOnTop**), transparente, sin decoraciones (sin barra de titulo nativa) y oculta de la barra de tareas (**skipTaskbar**), de 450x600 pixeles.
- **App.tsx** se conecta por WebSocket a **ws://127.0.0.1:8000/ws** y mantiene tres estados principales: **question**, **answer** y **opacity**. Al recibir cada tipo de evento del backend (**interim_question**, **question**, **answer_token**, **clear_answer**) actualiza la interfaz en tiempo real, con la pregunta resaltada en amarillo y las respuestas del LLM en verde esmeralda sobre un fondo oscuro translucido.
- **Permisos de Tauri v2**: al no tener una barra de titulo nativa, la ventana debia ser arrastrable y cerrable desde la propia interfaz web (**data-tauri-drag-region** y un boton de cierre). Esto inicialmente no funcionaba porque el sistema de permisos de Tauri v2 (**capabilities/default.json**) no incluia **core:window:allow-start-dragging** ni **core:window:allow-close**, dos permisos que no se otorgan por defecto por razones de seguridad.
- Se descarto explicitamente implementar un "modo sigilo" que ocultara la ventana de programas de captura de pantalla (Zoom, Teams, OBS) mediante la API de Windows **SetWindowDisplayAffinity**, por tratarse de una herramienta de evasion de deteccion que facilitaria el engaño a un entrevistador real.

# Fase 6: Carga dinamica de CV, soporte bilingue y traduccion en vivo

- **Carga dinamica de CV**: se agrego el endpoint **POST /upload-cv** en FastAPI, que recibe un PDF (**UploadFile**), extrae su texto con **pypdf**, y se lo envia a la nueva funcion **procesar_cv_pdf** en **llm_engine.py**. Esta funcion le pide a Groq, usando su modo de **salida JSON estructurada** (**response_format={"type": "json_object"}**), que resuma el CV en el mismo esquema que ya usaba **cv_mock.json**, y sobrescribe el archivo con el resultado. En el frontend, un boton discreto "Subir CV" en la barra superior abre el explorador de archivos y muestra "Cargando..." y luego "CV Actualizado" mientras el PDF se sube via **fetch**.
- **Deteccion bilingue**: se investigo pedir a Deepgram un parametro **detect_language**, pero se comprobo en vivo contra la API real que ese parametro no existe para el endpoint de streaming (devuelve un error 400). El mecanismo correcto y verificado es configurar **language="multi"**, que activa el modelo multilingue de Deepgram y agrega un campo **languages** (por ejemplo **["en"]**) a cada fragmento de transcripcion.
- **Traduccion en vivo**: cuando el sistema detecta que una pregunta fue hecha en ingles (revisando ese campo **languages**, con un respaldo heuristico por palabras clave si la metadata no esta disponible), lanza en paralelo una tarea liviana que llama a la nueva funcion **traducir_pregunta** en **llm_engine.py**. Esta funcion usa un modelo mas pequeño y rapido (**openai/gpt-oss-20b**) exclusivamente para traducir, sin competir con el modelo principal que genera los talking points. La traduccion llega al frontend como **{"type": "translation"}** y se muestra en gris claro, en cursiva, justo debajo de la pregunta original.
- **Candado de idioma adaptativo**: el System Prompt del motor LLM se actualizo para responder siempre en el mismo idioma de la pregunta (ingles o español), en lugar de forzar español de forma absoluta como en una version anterior, manteniendo intacta la regla de contingencia que impide respuestas del tipo "no lo se".

# Conclusion

Con estas seis fases, el Copiloto de Entrevistas cubre el flujo completo en tiempo real: escuchar el audio del sistema en cualquiera de los dos idiomas soportados, convertirlo en texto con streaming en vivo, generar y traducir sugerencias de respuesta basadas en un CV que el propio usuario puede actualizar subiendo un PDF, y mostrar todo en un overlay de escritorio nativo, robusto ante congelamientos e interrupciones.
"""


if __name__ == "__main__":
    pdf_path, docx_path = generate_report(REPORT_TITLE, REPORT_CONTENT)
    print(f"PDF generado en: {pdf_path}")
    print(f"Word generado en: {docx_path}")
