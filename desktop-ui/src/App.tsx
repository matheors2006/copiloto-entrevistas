import { useEffect, useRef, useState } from "react";
import "./App.css";

type ServerMessage =
  | { type: "question"; text: string }
  | { type: "answer_token"; text: string };

const WS_URL = "ws://127.0.0.1:8000/ws";
const SLATE_900_RGB = "15, 23, 42";
const OPACITY_STEP = 0.05;
const MIN_OPACITY = 0.3;
const MAX_OPACITY = 1;

function App() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [opacity, setOpacity] = useState(0.85);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const socket = new WebSocket(WS_URL);
    socketRef.current = socket;

    socket.onmessage = (event) => {
      const message: ServerMessage = JSON.parse(event.data);

      if (message.type === "question") {
        setQuestion(message.text);
        setAnswer("");
      } else if (message.type === "answer_token") {
        setAnswer((previous) => previous + message.text);
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

        <div className="flex gap-1">
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
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-white/40 mb-1">Pregunta</p>
          <p className="text-yellow-400 font-medium leading-snug">
            {question || "Esperando la siguiente pregunta..."}
          </p>
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