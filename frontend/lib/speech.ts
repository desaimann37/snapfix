"use client";

// Voice input: Web Speech API first (free, live transcript). If the browser lacks it, record audio with
// MediaRecorder and upload it for server-side transcription (faster-whisper). Typing always works.

import { useCallback, useEffect, useRef, useState } from "react";

type Recognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
};

function getRecognition(): (new () => Recognition) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export type VoiceMode = "speech" | "recorder" | "none";

export function useVoice(onFinalText: (text: string) => void) {
  const [mode, setMode] = useState<VoiceMode>("none");
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [audio, setAudio] = useState<Blob | null>(null);
  const recRef = useRef<Recognition | null>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const finalCb = useRef(onFinalText);
  finalCb.current = onFinalText;

  useEffect(() => {
    if (getRecognition()) setMode("speech");
    else if (typeof window !== "undefined" && "MediaRecorder" in window && navigator.mediaDevices !== undefined) setMode("recorder");
  }, []);

  const start = useCallback(async () => {
    setError(null);
    const Ctor = getRecognition();
    if (Ctor) {
      const rec = new Ctor();
      rec.lang = "en-US";
      rec.continuous = false;
      rec.interimResults = true;
      rec.onresult = (e) => {
        let interimText = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const r = e.results[i];
          if (r.isFinal) finalCb.current(r[0].transcript.trim());
          else interimText += r[0].transcript;
        }
        setInterim(interimText);
      };
      rec.onerror = (e) => {
        setError(e.error === "not-allowed" ? "Microphone permission was denied. You can type instead." : "Didn't catch that. Try again or type.");
        setListening(false);
      };
      rec.onend = () => {
        setListening(false);
        setInterim("");
      };
      recRef.current = rec;
      rec.start();
      setListening(true);
      return;
    }
    if (mode === "recorder") {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const chunks: BlobPart[] = [];
        const rec = new MediaRecorder(stream);
        rec.ondataavailable = (ev) => chunks.push(ev.data);
        rec.onstop = () => {
          stream.getTracks().forEach((t) => t.stop());
          setAudio(new Blob(chunks, { type: rec.mimeType || "audio/webm" }));
          setListening(false);
        };
        mediaRef.current = rec;
        rec.start();
        setListening(true);
        setTimeout(() => rec.state === "recording" && rec.stop(), 15000);
      } catch {
        setError("Microphone permission was denied. You can type instead.");
      }
    }
  }, [mode]);

  const stop = useCallback(() => {
    recRef.current?.stop();
    if (mediaRef.current?.state === "recording") mediaRef.current.stop();
  }, []);

  useEffect(() => () => recRef.current?.abort(), []);

  return { mode, listening, interim, error, audio, clearAudio: () => setAudio(null), start, stop };
}
