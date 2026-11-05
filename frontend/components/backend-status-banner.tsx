"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ExternalLink, Loader2, RefreshCw } from "lucide-react";

import { API_URL, probeBackend } from "@/lib/api";

const RENDER_SERVICE_URL = "https://dashboard.render.com/web/srv-dblotuk9v7es73cu9dpg";

export default function BackendStatusBanner() {
  const [checking, setChecking] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [isRender, setIsRender] = useState(false);

  const runProbe = useCallback(async () => {
    setChecking(true);
    const result = await probeBackend();
    setChecking(false);

    if (result.state === "healthy") {
      setMessage(null);
      setIsRender(false);
      return;
    }

    setMessage(result.message);
    setIsRender(API_URL.includes("onrender.com"));
  }, []);

  useEffect(() => {
    void runProbe();
  }, [runProbe]);

  if (!message) {
    return null;
  }

  return (
    <div className="mb-6 rounded-2xl border border-warning/30 bg-warning/5 p-4 text-sm">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
        <div className="min-w-0 flex-1">
          <p className="font-medium text-foreground">Processing service unavailable</p>
          <p className="mt-1 text-xs leading-5 text-text-secondary">{message}</p>
          <p className="mt-2 text-[11px] text-text-muted">
            API endpoint: <span className="font-mono">{API_URL}</span>
          </p>

          {isRender && (
            <div className="mt-3 rounded-xl border border-border/80 bg-surface/80 p-3 text-xs text-text-secondary">
              <p className="font-medium text-foreground">To restore uploads on Render</p>
              <ol className="mt-2 list-decimal space-y-1 pl-4 leading-5">
                <li>
                  Open the{" "}
                  <a
                    href={RENDER_SERVICE_URL}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-primary hover:underline"
                  >
                    backend service on Render
                    <ExternalLink className="h-3 w-3" />
                  </a>
                  .
                </li>
                <li>
                  If the service is <strong>Suspended</strong>, click Resume. If deploy
                  failed, open Logs and click <strong>Manual Deploy</strong>.
                </li>
                <li>
                  Wait until <code className="rounded bg-surface-soft px-1">/health</code>{" "}
                  returns JSON (not 404), then click Check again below.
                </li>
              </ol>
            </div>
          )}

          <button
            type="button"
            onClick={() => void runProbe()}
            disabled={checking}
            className="btn-secondary mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs"
          >
            {checking ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            Check again
          </button>
        </div>
      </div>
    </div>
  );
}
