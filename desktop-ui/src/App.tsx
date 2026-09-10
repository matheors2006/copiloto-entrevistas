import { useEffect, useRef, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import "./App.css";

type ServerMessage =
  | { type: "interim_question"; text: string }
  | { type: "question"; text: string }
  | { type: "answer_token"; text: string }
  | { type: "clear_answer" }
  | { type: "translation"; text: string };

type CvUploadStatus = "idle" | "loading" | "success" | "error";

const WS_URL = "ws://127.0.0.1:8000/ws";
const UPLOAD_CV_URL = "http://127.0.0.1:8000/upload-cv";
const SLATE_900_RGB = "15, 23, 42";
const OPACITY_STEP = 0.05;
const MIN_OPACITY = 0.3;
const MAX_OPACITY = 1;
const CV_STATUS_LABEL: Record<CvUploadStatus, string> = {
  idle: "Subir CV",
  loading: "Cargando...",
  success: "CV Actualizado",
  error: "Error al subir",
};

function App() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [translation, setTranslation] = useState("");
  const [opacity, setOpacity] = useState(0.85);
  const [cvStatus, setCvStatus] = useState<CvUploadStatus>("idle");
  const socketRef = useRef<WebSocket | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const socket = new WebSocket(WS_URL);
    socketRef.current = socket;

    socket.onmessage = (event) => {
      const message: ServerMessage = JSON.parse(event.data);

      if (message.type === "interim_question" || message.type === "question") {
        setQuestion(message.text);
        setAnswer("");
        setTranslation("");
      } else if (message.type === "answer_token") {
        setAnswer((previous) => previous + message.text);
      } else if (message.type === "clear_answer") {
        setAnswer("");
      } else if (message.type === "translation") {
        setTranslation(message.text);
      }
    };

    return () => {
      socket.close();
    };
  }, []);

  const increaseOpacity = () =>
    setOpacity((previous) => Math.min(MAX_OPACITY, +(previous + OPACITY_STEP).toFixed(2)));
  const decreaseOpacity = () =>
    setOpacity((previous) => Math.max(MIN_OPACITY, +(previous - OPACITY_STEP).toFixed(2)));
  const closeWindow = () => getCurrentWindow().close();

  const handleCvButtonClick = () => fileInputRef.current?.click();

  const handleCvFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setCvStatus("loading");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(UPLOAD_CV_URL, { method: "POST", body: formData });
      if (!response.ok) throw new Error("upload failed");
      setCvStatus("success");
    } catch {
      setCvStatus("error");
    } finally {
      setTimeout(() => setCvStatus("idle"), 2500);
    }
  };

  return (
    <div
      className="h-screen w-screen flex flex-col rounded-xl overflow-hidden text-white font-sans select-none"
      style={{ backgroundColor: `rgba(${SLATE_900_RGB}, ${opacity})` }}
    >
      <div
        data-tauri-drag-region
        className="flex items-center justify-between px-3 py-2 border-b border-white/10 cursor-move"
      >
        <button
          data-tauri-drag-region
          className="flex items-center gap-2 text-white/50 text-xs uppercase tracking-wide bg-transparent"
          title="Arrastrar ventana"
        >
          <span data-tauri-drag-region>⋮⋮</span>
          <span data-tauri-drag-region>Copiloto de Entrevistas</span>
        </button>

        <div className="flex items-center gap-1">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={handleCvFileChange}
          />
          <button
            onClick={handleCvButtonClick}
            disabled={cvStatus === "loading"}
            className="px-2 h-6 rounded bg-white/10 hover:bg-white/20 text-[10px] leading-none disabled:opacity-60"
            title="Subir CV en PDF"
          >
            {CV_STATUS_LABEL[cvStatus]}
          </button>
          <button
            onClick={decreaseOpacity}
            className="w-6 h-6 rounded bg-white/10 hover:bg-white/20 text-xs leading-none"
            title="Bajar opacidad"
          >
            -
          </button>
          <button
            onClick={increaseOpacity}
            className="w-6 h-6 rounded bg-white/10 hover:bg-white/20 text-xs leading-none"
            title="Subir opacidad"
          >
            +
          </button>
          <button
            onClick={closeWindow}
            className="w-6 h-6 rounded bg-white/10 hover:bg-red-500/70 text-xs leading-none"
            title="Cerrar ventana"
          >
            ×
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-white/40 mb-1">Pregunta</p>
          <p className="text-yellow-400 font-medium leading-snug">
            {question || "Esperando la siguiente pregunta..."}
          </p>
          {translation && <p className="text-white/40 italic text-sm mt-1">{translation}</p>}
        </div>

        <div>
          <p className="text-[11px] uppercase tracking-wide text-white/40 mb-1">Talking Points</p>
          <p className="text-emerald-400 leading-relaxed whitespace-pre-wrap">{answer}</p>
        </div>
      </div>
    </div>
  );
}

export default App;