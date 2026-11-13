import { useEffect, useRef, useState } from "react";
import type { HubStatus } from "./types";

type Role = "board" | "controller";

/**
 * Which board this browser belongs to. On a public server (PRIVATE_ROOMS=1) every visitor gets
 * their own room, shared by their board and controller tabs (same localStorage). Locally the
 * server ignores it and everyone shares one room. ?room=abc in the URL picks a room explicitly.
 */
export const ROOM: string = (() => {
  const make = () => Math.random().toString(36).slice(2, 12);
  const fromUrl = new URLSearchParams(location.search).get("room");
  try {
    const room = fromUrl || localStorage.getItem("adaptiboard.room") || make();
    localStorage.setItem("adaptiboard.room", room);
    return room;
  } catch {
    return fromUrl || make();
  }
})();

/** fetch() for /api calls, tagged with this browser's room. */
export function api(url: string, init: RequestInit = {}) {
  return fetch(url, { ...init, headers: { ...(init.headers || {}), "X-Room": ROOM } });
}
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
      const ws = new WebSocket(`${proto}://${location.host}/ws?role=${role}&room=${encodeURIComponent(ROOM)}`);
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
  const r = await api(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}
