import { useEffect, useRef, useState } from "react";
import type { HubStatus } from "./types";

type Role = "board" | "controller";
type Handler = (msg: any) => void;

/**
 * WebSocket connection to the AdaptiBoard server. Reconnects automatically,
 * so the board/controller survive the server restarting or Wi-Fi blips.
 */
export function useHub(role: Role, onMessage: Handler) {
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState<HubStatus | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const handlerRef = useRef(onMessage);
  handlerRef.current = onMessage;

  useEffect(() => {
    let closed = false;
    let retry: number | undefined;
    let ping: number | undefined;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws?role=${role}`);
      wsRef.current = ws;
      ws.onopen = () => {
        setConnected(true);
        ping = window.setInterval(() => ws.readyState === 1 && ws.send('{"type":"ping"}'), 15000);
      };
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === "status") setStatus(msg);
        handlerRef.current(msg);
      };
      ws.onclose = () => {
        setConnected(false);
        clearInterval(ping);
        if (!closed) retry = window.setTimeout(connect, 1200);
      };
      ws.onerror = () => ws.close();
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      clearInterval(ping);
      wsRef.current?.close();
    };
  }, [role]);

  const send = (msg: object) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
  };

  return { connected, status, send };
}

export async function postJSON<T = any>(url: string, body: object): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}
