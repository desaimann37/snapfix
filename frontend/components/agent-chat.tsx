"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, LoaderCircle, Send, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SimpleMarkdown } from "@/components/simple-markdown";
import { api, jsonBody, type AgentReply } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Msg {
  role: "user" | "assistant";
  content: string;
  tools?: AgentReply["tool_calls"];
  mode?: string;
}

const SUGGESTIONS = [
  "What's open in Engineering Hall over P2?",
  "Any hazards right now?",
  "Show root-cause clusters",
  "How are we doing today?",
];

/** Dispatcher chat: plain-English questions answered by the agent using read-only tools. */
export function AgentChat({ draftEmailFor }: { draftEmailFor?: string }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const suggestions = draftEmailFor ? [...SUGGESTIONS, `Draft a status update email for ${draftEmailFor}`] : SUGGESTIONS;

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [msgs, busy]);

  async function ask(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    const history = msgs.map((m) => ({ role: m.role, content: m.content }));
    setMsgs((m) => [...m, { role: "user", content: message }]);
    setInput("");
    setBusy(true);
    try {
      const r = await api<AgentReply>("/api/agent/chat", jsonBody({ message, history }));
      setMsgs((m) => [...m, { role: "assistant", content: r.answer, tools: r.tool_calls, mode: r.mode }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", content: `Sorry, that failed: ${e instanceof Error ? e.message : "error"}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-[440px] flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto pr-1" aria-live="polite">
        {msgs.length === 0 && (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">Ask about the work-order queue in plain English.</p>
            <div className="flex flex-wrap gap-1.5">
              {suggestions.map((s) => (
                <button key={s} onClick={() => ask(s)} className="rounded-full border px-3 py-1 text-xs hover:bg-accent">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={cn("flex gap-2", m.role === "user" && "justify-end")}>
            {m.role === "assistant" && (
              <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground" aria-hidden="true">
                <Bot className="size-4" />
              </span>
            )}
            <div
              className={cn(
                "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                m.role === "user" ? "bg-primary text-primary-foreground" : "border bg-card",
              )}
            >
              {m.role === "assistant" ? <SimpleMarkdown text={m.content} /> : m.content}
              {m.tools && m.tools.length > 0 && (
                <p className="mt-2 flex flex-wrap items-center gap-1 border-t pt-1.5 text-[11px] text-muted-foreground">
                  <Wrench className="size-3" aria-hidden="true" />
                  {m.tools.map((t) => `${t.name} → ${t.summary}`).join(" · ")}
                  {m.mode && m.mode !== "live" && <span>· {m.mode === "mock" ? "offline demo mode" : m.mode}</span>}
                </p>
              )}
            </div>
          </div>
        ))}
        {busy && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> Looking that up…
          </p>
        )}
        <div ref={endRef} />
      </div>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
      >
        <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask the dispatcher assistant…" aria-label="Message the assistant" />
        <Button type="submit" size="icon" disabled={busy || !input.trim()} aria-label="Send">
          <Send />
        </Button>
      </form>
    </div>
  );
}
