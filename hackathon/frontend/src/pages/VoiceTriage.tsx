import { useState, useRef, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Mic,
  PhoneOff,
  Radio,
  Volume2,
  User,
  Bot,
  Phone,
  Settings2,
} from "lucide-react";
import { useToast } from "@/components/ui/use-toast";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface Message {
  role: "user" | "ai";
  text: string;
  timestamp?: string;
}

// ── Silence / VAD Detection Config ────────────────────────────
const SILENCE_THRESHOLD = 0.015; // RMS below this = silence
const SILENCE_DURATION_MS = 1800; // 1.8s of silence → auto-stop
const MIN_RECORDING_MS = 600; // Minimum recording to avoid empty clips
const MAX_RECORDING_MS = 30000; // 30s max per turn

const VoiceTriage = () => {
  const { toast } = useToast();

  // ── State ──────────────────────────────────────────────────
  const [callState, setCallState] = useState<
    "idle" | "connecting" | "active" | "ended"
  >("idle");
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<Message[]>([]);
  const [status, setStatus] = useState("Press Call to start");
  const [audioLevel, setAudioLevel] = useState(0);
  const [handsFree, setHandsFree] = useState(true);
  const [callDuration, setCallDuration] = useState(0);

  // ── Refs ───────────────────────────────────────────────────
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const silenceTimerRef = useRef<number | null>(null);
  const recordingStartRef = useRef<number>(0);
  const maxRecordingTimerRef = useRef<number | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const callTimerRef = useRef<number | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);
  const isPlayingRef = useRef(false);
  const isProcessingRef = useRef(false);
  const sessionIdRef = useRef<string | null>(null);
  const callStateRef = useRef<string>("idle");

  // Keep refs in sync
  useEffect(() => {
    isPlayingRef.current = isPlaying;
  }, [isPlaying]);
  useEffect(() => {
    isProcessingRef.current = isProcessing;
  }, [isProcessing]);
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);
  useEffect(() => {
    callStateRef.current = callState;
  }, [callState]);

  // Auto-scroll transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript]);

  // Call duration timer
  useEffect(() => {
    if (callState === "active") {
      setCallDuration(0);
      callTimerRef.current = window.setInterval(() => {
        setCallDuration((d) => d + 1);
      }, 1000);
    } else {
      if (callTimerRef.current) clearInterval(callTimerRef.current);
    }
    return () => {
      if (callTimerRef.current) clearInterval(callTimerRef.current);
    };
  }, [callState]);

  const formatDuration = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m.toString().padStart(2, "0")}:${sec.toString().padStart(2, "0")}`;
  };

  // ── Audio Level Monitor ────────────────────────────────────
  const startAudioMonitor = useCallback((stream: MediaStream) => {
    const ctx = new AudioContext();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    audioContextRef.current = ctx;
    analyserRef.current = analyser;

    const dataArray = new Float32Array(analyser.fftSize);

    const monitor = () => {
      analyser.getFloatTimeDomainData(dataArray);
      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        sum += dataArray[i] * dataArray[i];
      }
      const rms = Math.sqrt(sum / dataArray.length);
      setAudioLevel(Math.min(rms * 8, 1)); // Scale for visual
      animFrameRef.current = requestAnimationFrame(monitor);
    };
    monitor();
  }, []);

  const stopAudioMonitor = useCallback(() => {
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    animFrameRef.current = null;
    setAudioLevel(0);
  }, []);

  // ── Get RMS for silence detection ──────────────────────────
  const getRMS = useCallback(() => {
    if (!analyserRef.current) return 0;
    const dataArray = new Float32Array(analyserRef.current.fftSize);
    analyserRef.current.getFloatTimeDomainData(dataArray);
    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i] * dataArray[i];
    }
    return Math.sqrt(sum / dataArray.length);
  }, []);

  // ── Start Session (Call 911) ───────────────────────────────
  const startSession = async () => {
    try {
      setCallState("connecting");
      setStatus("Connecting...");

      // Get mic permission early
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;
      startAudioMonitor(stream);

      // Start backend session
      const res = await fetch(`${API_BASE}/api/interview/start`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Failed to start session");

      const data = await res.json();
      setSessionId(data.session_id);
      setTranscript([
        {
          role: "ai",
          text: data.ai_message,
          timestamp: new Date().toLocaleTimeString(),
        },
      ]);
      setCallState("active");
      setStatus("Connected");

      // Play greeting, then auto-record
      await playTTS(data.ai_message);
    } catch (err) {
      console.error(err);
      toast({
        title: "Connection Failed",
        description: "Could not connect to triage server.",
        variant: "destructive",
      });
      setCallState("idle");
      setStatus("Connection failed. Try again.");
      cleanupStream();
    }
  };

  // ── Cleanup mic stream ─────────────────────────────────────
  const cleanupStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    stopAudioMonitor();
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    analyserRef.current = null;
  }, [stopAudioMonitor]);

  // ── Start Recording ────────────────────────────────────────
  const startRecording = useCallback(() => {
    if (!streamRef.current || isPlayingRef.current || isProcessingRef.current)
      return;
    if (callStateRef.current !== "active") return;

    try {
      const mediaRecorder = new MediaRecorder(streamRef.current, {
        mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "audio/webm",
      });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      recordingStartRef.current = Date.now();

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const duration = Date.now() - recordingStartRef.current;
        if (duration < MIN_RECORDING_MS || audioChunksRef.current.length === 0) {
          // Too short — restart recording if hands-free
          if (handsFree && callStateRef.current === "active") {
            setTimeout(() => startRecording(), 300);
          }
          return;
        }
        const audioBlob = new Blob(audioChunksRef.current, {
          type: "audio/webm",
        });
        await processAudio(audioBlob);
      };

      mediaRecorder.start(250); // Collect in 250ms chunks
      setIsRecording(true);
      setStatus("Listening...");

      // Silence detection via polling
      let silentSince: number | null = null;

      const checkSilence = () => {
        if (!mediaRecorderRef.current || mediaRecorderRef.current.state !== "recording") return;

        const rms = getRMS();
        const elapsed = Date.now() - recordingStartRef.current;

        if (rms < SILENCE_THRESHOLD) {
          if (!silentSince) silentSince = Date.now();
          if (elapsed > MIN_RECORDING_MS && Date.now() - silentSince > SILENCE_DURATION_MS) {
            // Silence detected — stop recording
            stopRecordingInternal();
            return;
          }
        } else {
          silentSince = null;
        }

        silenceTimerRef.current = window.setTimeout(checkSilence, 100);
      };
      checkSilence();

      // Max recording safety
      maxRecordingTimerRef.current = window.setTimeout(() => {
        stopRecordingInternal();
      }, MAX_RECORDING_MS);
    } catch (err) {
      console.error("Recording start failed:", err);
    }
  }, [getRMS, handsFree]);

  // ── Stop Recording (internal) ──────────────────────────────
  const stopRecordingInternal = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (maxRecordingTimerRef.current) {
      clearTimeout(maxRecordingTimerRef.current);
      maxRecordingTimerRef.current = null;
    }
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state === "recording"
    ) {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  }, []);

  // ── Manual stop (push-to-talk mode) ────────────────────────
  const stopRecordingManual = useCallback(() => {
    stopRecordingInternal();
  }, [stopRecordingInternal]);

  // ── Process Audio ──────────────────────────────────────────
  const processAudio = async (audioBlob: Blob) => {
    if (!sessionIdRef.current) return;
    setIsProcessing(true);
    setStatus("Processing speech...");

    try {
      // 1. STT
      const formData = new FormData();
      formData.append("audio", audioBlob, "voice.webm");

      const sttRes = await fetch(`${API_BASE}/api/interview/stt`, {
        method: "POST",
        body: formData,
      });

      if (!sttRes.ok) throw new Error("STT failed");
      const sttData = await sttRes.json();
      const userText = sttData.text;

      if (!userText || !userText.trim()) {
        setStatus("Didn't catch that");
        setIsProcessing(false);
        // Restart recording in hands-free
        if (handsFree && callStateRef.current === "active") {
          setTimeout(() => startRecording(), 500);
        }
        return;
      }

      // Filter Whisper hallucinations
      const hallucinations = new Set([
        "thank you.",
        "thanks for watching.",
        "you",
        "bye.",
        "...",
        "thank you for watching.",
        "thanks.",
        "the end.",
        "subscribe.",
      ]);
      if (hallucinations.has(userText.trim().toLowerCase())) {
        setStatus("Didn't catch that. Try again.");
        setIsProcessing(false);
        if (handsFree && callStateRef.current === "active") {
          setTimeout(() => startRecording(), 500);
        }
        return;
      }

      setTranscript((prev) => [
        ...prev,
        {
          role: "user",
          text: userText,
          timestamp: new Date().toLocaleTimeString(),
        },
      ]);
      setStatus("AI thinking...");

      // 2. Send to conversation engine
      const msgRes = await fetch(
        `${API_BASE}/api/interview/${sessionIdRef.current}/message`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: userText }),
        }
      );

      if (!msgRes.ok) throw new Error("AI failed");
      const msgData = await msgRes.json();
      const aiText = msgData.ai_message;

      setTranscript((prev) => [
        ...prev,
        {
          role: "ai",
          text: aiText,
          timestamp: new Date().toLocaleTimeString(),
        },
      ]);

      setIsProcessing(false);
      setStatus("AI speaking...");

      // 3. TTS → then auto-record
      await playTTS(aiText);

      if (msgData.is_complete) {
        setCallState("ended");
        setStatus("Triage complete");
        cleanupStream();
        toast({
          title: "Triage Complete",
          description:
            "Your emergency report has been submitted. A responder will follow up.",
        });
      }
    } catch (err) {
      console.error(err);
      setIsProcessing(false);
      setStatus("Error. Retrying...");
      toast({
        title: "Error",
        description: "Failed to process voice. Retrying...",
        variant: "destructive",
      });
      // Retry recording
      if (handsFree && callStateRef.current === "active") {
        setTimeout(() => startRecording(), 1000);
      }
    }
  };

  // ── Play TTS ───────────────────────────────────────────────
  const playTTS = async (text: string) => {
    try {
      setIsPlaying(true);
      setStatus("AI speaking...");

      // Fetch audio from backend (uses ElevenLabs → Edge-TTS → fallback chain)
      const res = await fetch(`${API_BASE}/api/interview/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });

      if (!res.ok) throw new Error(`TTS failed: ${res.status}`);

      const contentType = res.headers.get("content-type") || "";

      // If backend returned JSON, it means all server TTS failed → use browser TTS
      if (contentType.includes("application/json")) {
        const data = await res.json();
        if (data.fallback) {
          console.log("Using browser TTS fallback");
          await playBrowserTTS(text);
          setIsPlaying(false);
          onTTSFinished();
          return;
        }
      }

      // Play the audio blob (MP3 from ElevenLabs or Edge-TTS)
      const blob = await res.blob();
      if (blob.size === 0) throw new Error("Empty audio response");

      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioPlayerRef.current = audio;

      await new Promise<void>((resolve) => {
        audio.onended = () => {
          URL.revokeObjectURL(url);
          resolve();
        };
        audio.onerror = (e) => {
          console.warn("Audio playback error:", e);
          URL.revokeObjectURL(url);
          resolve();
        };
        audio.play().catch((e) => {
          console.warn("Audio play() rejected:", e);
          URL.revokeObjectURL(url);
          resolve();
        });
      });

      setIsPlaying(false);
      onTTSFinished();
    } catch (err) {
      console.error("TTS error, falling back to browser TTS:", err);
      // Browser TTS final fallback
      try {
        await playBrowserTTS(text);
      } catch (e) {
        console.error("Browser TTS also failed:", e);
      }
      setIsPlaying(false);
      onTTSFinished();
    }
  };

  // ── Browser TTS fallback ───────────────────────────────────
  const playBrowserTTS = (text: string): Promise<void> => {
    return new Promise<void>((resolve) => {
      if (!window.speechSynthesis) {
        resolve();
        return;
      }
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      utterance.onend = () => resolve();
      utterance.onerror = () => resolve();
      // Safety timeout in case speech synthesis hangs
      const timeout = setTimeout(() => resolve(), 15000);
      utterance.onend = () => { clearTimeout(timeout); resolve(); };
      utterance.onerror = () => { clearTimeout(timeout); resolve(); };
      window.speechSynthesis.speak(utterance);
    });
  };

  // ── After TTS finishes → auto-record ──────────────────────
  const onTTSFinished = useCallback(() => {
    if (handsFree && callStateRef.current === "active") {
      // Small pause before listening
      setTimeout(() => {
        if (callStateRef.current === "active" && !isProcessingRef.current) {
          startRecording();
        }
      }, 400);
    } else {
      setStatus("Your turn — press mic to speak");
    }
  }, [handsFree, startRecording]);

  // ── End Call ───────────────────────────────────────────────
  const handleEndCall = async () => {
    stopRecordingInternal();

    if (sessionIdRef.current) {
      try {
        const res = await fetch(
          `${API_BASE}/api/interview/${sessionIdRef.current}/end`,
          { method: "POST" }
        );
        if (res.ok) {
          const data = await res.json();
          if (data.report) {
            toast({
              title: "Triage Complete",
              description: "Report generated from collected data.",
            });
          }
        }
      } catch (e) {
        console.error(e);
      }
    }

    setSessionId(null);
    setCallState("ended");
    setStatus("Call ended");
    cleanupStream();

    if (audioPlayerRef.current) {
      audioPlayerRef.current.pause();
      audioPlayerRef.current = null;
    }
    window.speechSynthesis.cancel();
  };

  // ── New Call ───────────────────────────────────────────────
  const handleNewCall = () => {
    setTranscript([]);
    setCallState("idle");
    setCallDuration(0);
    setStatus("Press Call to start");
  };

  // ── Cleanup on unmount ─────────────────────────────────────
  useEffect(() => {
    return () => {
      cleanupStream();
      if (audioPlayerRef.current) audioPlayerRef.current.pause();
      window.speechSynthesis.cancel();
      if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
      if (maxRecordingTimerRef.current)
        clearTimeout(maxRecordingTimerRef.current);
    };
  }, [cleanupStream]);

  // ── Audio Waveform Bars ────────────────────────────────────
  const WaveformBars = ({ active, level }: { active: boolean; level: number }) => {
    const bars = 24;
    return (
      <div className="flex items-center justify-center gap-[2px] h-12">
        {Array.from({ length: bars }).map((_, i) => {
          const distance = Math.abs(i - bars / 2) / (bars / 2);
          const height = active
            ? Math.max(4, (1 - distance * 0.5) * level * 48 + Math.sin(Date.now() / 100 + i) * level * 8)
            : 4;
          return (
            <div
              key={i}
              className={`w-[3px] rounded-full transition-all duration-75 ${
                active
                  ? isRecording
                    ? "bg-red-500"
                    : "bg-emerald-500"
                  : "bg-slate-700"
              }`}
              style={{ height: `${Math.max(4, height)}px` }}
            />
          );
        })}
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 flex flex-col items-center justify-center p-4 relative overflow-hidden">
      {/* Background ambient effects */}
      {callState === "active" && (
        <>
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div
              className={`w-[500px] h-[500px] rounded-full transition-opacity duration-1000 ${
                isRecording
                  ? "bg-red-500/5 opacity-100"
                  : isPlaying
                  ? "bg-emerald-500/5 opacity-100"
                  : "opacity-0"
              }`}
              style={{
                transform: `scale(${1 + audioLevel * 0.3})`,
                transition: "transform 0.1s ease-out",
              }}
            />
          </div>
          {isRecording && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="w-64 h-64 bg-red-500/10 rounded-full animate-ping" style={{ animationDuration: "2s" }} />
            </div>
          )}
        </>
      )}

      <div className="w-full max-w-lg space-y-6 relative z-10">
        {/* Header */}
        <div className="text-center space-y-1">
          <div className="inline-flex items-center justify-center p-3 bg-red-500/10 rounded-full mb-2">
            <Radio
              className={`w-7 h-7 ${
                callState === "active"
                  ? "text-red-500 animate-pulse"
                  : "text-slate-500"
              }`}
            />
          </div>
          <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
            2020 AI Agent — Voice Triage
          </h1>
          {callState === "active" && (
            <p className="text-xs font-mono text-red-400">
              {formatDuration(callDuration)}
            </p>
          )}
        </div>

        {/* Main Call Card */}
        <Card className="bg-slate-900/60 border-slate-800 p-6 backdrop-blur-xl shadow-2xl">
          <div className="flex flex-col items-center gap-6">
            {/* Status Text */}
            <div className="flex items-center gap-2">
              <div
                className={`w-2 h-2 rounded-full ${
                  callState === "active"
                    ? isRecording
                      ? "bg-red-500 animate-pulse"
                      : isPlaying
                      ? "bg-emerald-500 animate-pulse"
                      : isProcessing
                      ? "bg-amber-500 animate-pulse"
                      : "bg-blue-500"
                    : callState === "connecting"
                    ? "bg-amber-500 animate-pulse"
                    : "bg-slate-600"
                }`}
              />
              <p className="text-sm text-slate-400">{status}</p>
            </div>

            {/* Waveform Visualizer */}
            <div className="w-full py-2">
              <WaveformBars
                active={isRecording || isPlaying}
                level={isRecording ? audioLevel : isPlaying ? 0.4 : 0}
              />
            </div>

            {/* Controls */}
            <div className="flex items-center gap-6">
              {callState === "idle" ? (
                <Button
                  size="lg"
                  className="bg-emerald-600 hover:bg-emerald-700 text-white rounded-full h-20 w-20 p-0 shadow-lg shadow-emerald-900/30 transition-transform hover:scale-105"
                  onClick={startSession}
                >
                  <Phone className="w-8 h-8" />
                </Button>
              ) : callState === "ended" ? (
                <Button
                  size="lg"
                  className="bg-blue-600 hover:bg-blue-700 text-white rounded-full h-16 w-48 text-base font-semibold shadow-lg"
                  onClick={handleNewCall}
                >
                  New Call
                </Button>
              ) : callState === "connecting" ? (
                <div className="flex flex-col items-center gap-3">
                  <div className="h-20 w-20 rounded-full bg-slate-800 border-2 border-amber-500/50 flex items-center justify-center">
                    <div className="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
                  </div>
                  <p className="text-xs text-slate-500">Setting up call...</p>
                </div>
              ) : (
                <>
                  {/* Hands-free toggle */}
                  <Button
                    size="sm"
                    variant="ghost"
                    className={`rounded-full h-10 w-10 p-0 ${
                      handsFree
                        ? "text-emerald-400 bg-emerald-500/10"
                        : "text-slate-500"
                    }`}
                    onClick={() => setHandsFree(!handsFree)}
                    title={
                      handsFree ? "Hands-free ON" : "Push-to-talk mode"
                    }
                  >
                    <Settings2 className="w-4 h-4" />
                  </Button>

                  {/* Mic button */}
                  {!handsFree && (
                    <Button
                      size="lg"
                      variant={isRecording ? "destructive" : "secondary"}
                      className={`rounded-full h-20 w-20 p-0 shadow-lg transition-transform ${
                        isRecording ? "scale-110" : "hover:scale-105"
                      } ${isProcessing || isPlaying ? "opacity-50" : ""}`}
                      onMouseDown={() =>
                        !isProcessing && !isPlaying && startRecording()
                      }
                      onMouseUp={stopRecordingManual}
                      onTouchStart={() =>
                        !isProcessing && !isPlaying && startRecording()
                      }
                      onTouchEnd={stopRecordingManual}
                      disabled={isProcessing || isPlaying}
                    >
                      <Mic
                        className={`w-8 h-8 ${
                          isRecording ? "animate-pulse" : ""
                        }`}
                      />
                    </Button>
                  )}

                  {/* In hands-free mode, show listening indicator */}
                  {handsFree && (
                    <div
                      className={`rounded-full h-20 w-20 flex items-center justify-center border-2 transition-all ${
                        isRecording
                          ? "border-red-500 bg-red-500/10"
                          : isPlaying
                          ? "border-emerald-500 bg-emerald-500/10"
                          : isProcessing
                          ? "border-amber-500 bg-amber-500/10"
                          : "border-slate-700 bg-slate-800"
                      }`}
                    >
                      {isRecording ? (
                        <Mic className="w-8 h-8 text-red-500 animate-pulse" />
                      ) : isPlaying ? (
                        <Volume2 className="w-8 h-8 text-emerald-500 animate-pulse" />
                      ) : isProcessing ? (
                        <div className="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
                      ) : (
                        <Mic className="w-8 h-8 text-slate-600" />
                      )}
                    </div>
                  )}

                  {/* Hang up */}
                  <Button
                    size="lg"
                    className="rounded-full h-14 w-14 p-0 bg-red-600 hover:bg-red-700 text-white shadow-lg shadow-red-900/30 transition-transform hover:scale-105"
                    onClick={handleEndCall}
                  >
                    <PhoneOff className="w-6 h-6" />
                  </Button>
                </>
              )}
            </div>

            {/* Mode indicator */}
            {callState === "active" && (
              <p className="text-[11px] text-slate-600">
                {handsFree
                  ? "Hands-free mode — speak naturally"
                  : "Push-to-talk — hold mic button to speak"}
              </p>
            )}
          </div>
        </Card>

        {/* Transcript */}
        {transcript.length > 0 && (
          <Card className="bg-black/30 border-slate-800/50 backdrop-blur-sm overflow-hidden">
            <div className="p-3 border-b border-slate-800/50">
              <span className="text-[10px] font-mono uppercase text-slate-500 tracking-wider">
                Live Transcript
              </span>
            </div>
            <div className="p-3 max-h-64 overflow-y-auto space-y-3">
              {transcript.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex gap-2 ${
                    msg.role === "user" ? "justify-end" : "justify-start"
                  }`}
                >
                  {msg.role === "ai" && (
                    <div className="w-6 h-6 rounded-full bg-red-500/20 flex-shrink-0 flex items-center justify-center mt-0.5">
                      <Bot className="w-3.5 h-3.5 text-red-400" />
                    </div>
                  )}
                  <div className="flex flex-col gap-0.5 max-w-[80%]">
                    <div
                      className={`rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
                        msg.role === "user"
                          ? "bg-blue-600 text-white rounded-tr-sm"
                          : "bg-slate-800/80 text-slate-200 rounded-tl-sm"
                      }`}
                    >
                      {msg.text}
                    </div>
                    {msg.timestamp && (
                      <span
                        className={`text-[10px] text-slate-600 ${
                          msg.role === "user" ? "text-right" : "text-left"
                        }`}
                      >
                        {msg.timestamp}
                      </span>
                    )}
                  </div>
                  {msg.role === "user" && (
                    <div className="w-6 h-6 rounded-full bg-blue-500/20 flex-shrink-0 flex items-center justify-center mt-0.5">
                      <User className="w-3.5 h-3.5 text-blue-400" />
                    </div>
                  )}
                </div>
              ))}

              {/* Processing indicator */}
              {isProcessing && (
                <div className="flex gap-2">
                  <div className="w-6 h-6 rounded-full bg-red-500/20 flex-shrink-0 flex items-center justify-center">
                    <Bot className="w-3.5 h-3.5 text-red-400" />
                  </div>
                  <div className="bg-slate-800/80 rounded-2xl rounded-tl-sm px-3.5 py-2">
                    <div className="flex gap-1.5">
                      <div className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                      <div className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                      <div className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                    </div>
                  </div>
                </div>
              )}

              <div ref={transcriptEndRef} />
            </div>
          </Card>
        )}

        {/* Info */}
        {callState === "idle" && (
          <div className="text-center space-y-2">
            <p className="text-xs text-slate-500 max-w-sm mx-auto leading-relaxed">
              Press the call button to speak with our AI triage operator.
              No phone needed — everything works in your browser.
              Describe your emergency and the AI will assess the situation.
            </p>
            <p className="text-[10px] text-slate-600">
              Requires microphone access. Works best in Chrome/Edge.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default VoiceTriage;
