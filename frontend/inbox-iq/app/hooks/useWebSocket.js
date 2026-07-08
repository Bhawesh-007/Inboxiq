"use client";
import { useEffect, useState, useRef, useCallback } from "react";

// Use the production Railway URL for WebSockets (wss:// for secure websocket)
const WS_BASE = "wss://inboxiq-production-ec9c.up.railway.app";

/**
 * useWebSocket
 *
 * Opens a WebSocket connection to /ws/emails/{userId} once userId is known.
 * Parses incoming { type: "new_emails", emails: [...] } messages.
 *
 * @param {string|null} userId  - Supabase UUID; hook is a no-op until this is set
 * @returns {{ newEmails: Array, clearNewEmails: Function, wsStatus: string }}
 */
export function useWebSocket(userId) {
  const [newEmails, setNewEmails] = useState([]);
  const [wsStatus, setWsStatus]   = useState("idle"); // idle | connecting | open | closed | error
  const wsRef = useRef(null);

  useEffect(() => {
    if (!userId) return;

    const url = `${WS_BASE}/ws/emails/${userId}`;
    console.log(`[WS] Connecting to ${url}`);
    setWsStatus("connecting");

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("[WS] Connection established");
      setWsStatus("open");
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "new_emails" && Array.isArray(msg.emails) && msg.emails.length > 0) {
          console.log(`[WS] Received ${msg.emails.length} new email(s)`);
          setNewEmails((prev) => [...msg.emails, ...prev]);
        }
      } catch (err) {
        console.error("[WS] Failed to parse message:", err);
      }
    };

    ws.onerror = (err) => {
      console.error("[WS] Error:", err);
      setWsStatus("error");
    };

    ws.onclose = (event) => {
      console.log(`[WS] Closed — code=${event.code}`);
      setWsStatus("closed");
    };

    // Cleanup: close socket when userId changes or component unmounts
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [userId]);

  const clearNewEmails = useCallback(() => setNewEmails([]), []);

  return { newEmails, clearNewEmails, wsStatus };
}
