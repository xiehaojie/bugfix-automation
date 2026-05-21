import { type Dispatch, type SetStateAction, useEffect } from "react";

import type { LogPayload } from "../types";

type LogStreamEvent = LogPayload & {
  type?: "snapshot" | "append";
  reset?: boolean;
};

export function useLogPolling(
  branch: string | undefined,
  setLogPayload: Dispatch<SetStateAction<LogPayload>>,
  refreshLog: (branch: string) => void | Promise<void>,
  apiPort?: number,
) {
  useEffect(() => {
    if (!branch) {
      setLogPayload({ branch: "", path: "", content: "" });
      return;
    }

    const source = new EventSource(logStreamUrl(branch, apiPort));
    let closed = false;
    let fallbackTimer: number | undefined;

    const pollFallback = async () => {
      try {
        await refreshLog(branch);
      } catch {
        // The API can be temporarily unavailable while the approval server restarts.
        // Keep the UI mounted and let the next fallback tick try again.
      }
    };

    const startPollingFallback = () => {
      if (closed || fallbackTimer !== undefined) return;
      source.close();
      void pollFallback();
      fallbackTimer = window.setInterval(() => {
        void pollFallback();
      }, 2000);
    };

    source.onmessage = (event) => {
      const payload = JSON.parse(event.data) as LogStreamEvent;
      if (closed || payload.branch !== branch) return;

      setLogPayload((current) => {
        if (payload.type === "snapshot" || payload.reset) {
          return payload;
        }
        if (!payload.content) return current;
        const content = current.branch === branch ? `${current.content}${payload.content}` : payload.content;
        return { ...current, ...payload, content };
      });
    };

    source.onerror = startPollingFallback;

    return () => {
      closed = true;
      if (fallbackTimer !== undefined) window.clearInterval(fallbackTimer);
      source.close();
    };
  }, [apiPort, branch, refreshLog, setLogPayload]);
}

function logStreamUrl(branch: string, apiPort?: number): string {
  const path = `/api/logs/stream?branch=${encodeURIComponent(branch)}`;
  if (!apiPort || typeof window === "undefined") return path;
  return `${window.location.protocol}//${window.location.hostname}:${apiPort}${path}`;
}
