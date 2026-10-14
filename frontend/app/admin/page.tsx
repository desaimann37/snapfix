"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { CloudOff, KeyRound, LoaderCircle, QrCode, RotateCcw, Sparkles, Wifi } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { api, jsonBody } from "@/lib/api";

const TOKEN_KEY = "snapfix.adminToken";

interface Health {
  status: string;
  db: boolean;
  llm_mode: string;
  embedder: string;
  sse_subscribers: number;
}

/**
 * Hidden operator console (not linked in the nav): offline-mock fallback switch for the live demo,
 * one-click demo reset, and health at a glance. Every action needs ADMIN_TOKEN.
 */
export default function AdminPage() {
  const [token, setToken] = useState("");
  const [health, setHealth] = useState<Health | null>(null);
  const [override, setOverride] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const headers = useCallback((t = token) => ({ "X-Admin-Token": t }), [token]);

  const refresh = useCallback(
    async (t = token) => {
      setHealth(await api<Health>("/api/health"));
      if (!t) return;
      try {
        const mode = await api<{ override: string | null; effective: string }>("/api/admin/llm-mode", { headers: headers(t) });
        setOverride(mode.override);
        setMsg(null);
      } catch {
        setMsg("Admin token rejected.");
      }
    },
    [token, headers],
  );

  useEffect(() => {
    let saved = "";
    try {
      saved = window.sessionStorage.getItem(TOKEN_KEY) ?? "";
    } catch {
      /* storage unavailable */
    }
    setToken(saved);
    refresh(saved).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function saveToken(t: string) {
    setToken(t);
    try {
      window.sessionStorage.setItem(TOKEN_KEY, t);
    } catch {
      /* ignore */
    }
  }

  async function setMode(mode: "live" | "mock" | null) {
    setBusy(`mode-${mode}`);
    try {
      await api("/api/admin/llm-mode", { ...jsonBody({ mode }), headers: { "Content-Type": "application/json", ...headers() } });
      await refresh();
      setMsg(mode === "mock" ? "Offline mock mode ON: no API calls." : mode === "live" ? "Live AI requested." : "Following LLM_MODE.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(null);
    }
  }

  async function reset() {
    if (!window.confirm("Reset all demo data to the starting state?")) return;
    setBusy("reset");
    try {
      const r = await api<{ summary: { tickets: number; clusters: number; seconds: number } }>("/api/admin/demo-reset", {
        method: "POST",
        headers: headers(),
      });
      setMsg(`Demo reset: ${r.summary.tickets} tickets, ${r.summary.clusters} cluster(s), ${r.summary.seconds}s.`);
      await refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Reset failed");
    } finally {
      setBusy(null);
    }
  }

  const live = health?.llm_mode === "live";
  return (
    <div className="mx-auto max-w-2xl space-y-6 px-4 py-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Operator console</h1>
        <p className="text-sm text-muted-foreground">Demo controls. Not linked from the app; requires the admin token.</p>
      </div>

      <Card>
        <CardContent className="space-y-2 pt-5">
          <Label htmlFor="token" className="flex items-center gap-1.5">
            <KeyRound className="size-4" aria-hidden="true" /> Admin token
          </Label>
          <div className="flex gap-2">
            <Input id="token" type="password" value={token} onChange={(e) => saveToken(e.target.value)} placeholder="ADMIN_TOKEN" />
            <Button variant="outline" onClick={() => refresh()}>Check</Button>
          </div>
          {msg && <p role="status" className="text-sm">{msg}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">AI mode</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="flex items-center gap-2 text-sm">
            {live ? <Wifi className="size-4 text-success" aria-hidden="true" /> : <CloudOff className="size-4 text-p2" aria-hidden="true" />}
            Currently <strong>{health ? (live ? "live (Claude)" : "offline mock") : "…"}</strong>
            {override && <span className="text-muted-foreground">· override: {override}</span>}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant={live ? "outline" : "default"} onClick={() => setMode("mock")} disabled={!token || busy !== null}>
              {busy === "mode-mock" ? <LoaderCircle className="animate-spin" /> : <CloudOff />} Force offline mock
            </Button>
            <Button variant="outline" onClick={() => setMode("live")} disabled={!token || busy !== null}>
              <Sparkles /> Use live AI
            </Button>
            <Button variant="ghost" onClick={() => setMode(null)} disabled={!token || busy !== null}>
              Follow LLM_MODE
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            If the venue Wi-Fi or the API fails mid-demo, switch to offline mock: every flow keeps working with deterministic
            results (hazard rules, dedupe and routing are unchanged). Live mode needs ANTHROPIC_API_KEY.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Demo data</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <Button variant="destructive" onClick={reset} disabled={!token || busy !== null}>
            {busy === "reset" ? <LoaderCircle className="animate-spin" /> : <RotateCcw />} Reset to demo start
          </Button>
          <Button asChild variant="outline">
            <Link href="/admin/qr">
              <QrCode /> QR sticker sheet
            </Link>
          </Button>
        </CardContent>
      </Card>

      {health && (
        <p className="text-xs text-muted-foreground">
          API {health.status} · database {health.db ? "ok" : "down"} · embeddings {health.embedder} · {health.sse_subscribers} live
          dashboard connection(s)
        </p>
      )}
    </div>
  );
}
