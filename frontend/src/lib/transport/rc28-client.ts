/**
 * RC-28 channel client (/api/v1/rc28): receives the server's decoded wheel
 * and key events and sends the LED state. Reconnects with backoff.
 */
import { controllerClient } from './controller-client';
import { authenticatedWsUrl } from './ws-url';

export type Rc28Key = 'transmit' | 'f1' | 'f2';

export type Rc28Message =
  | { type: 'status'; connected: boolean; available: boolean }
  | { type: 'rotate'; ticks: number }
  | { type: 'key'; key: Rc28Key; pressed: boolean };

export interface Rc28Leds {
  tx: boolean;
  f1: boolean;
  f2: boolean;
  link: boolean;
}

export interface Rc28Connection {
  setLeds(leds: Rc28Leds): void;
  close(): void;
}

const KEYS: readonly Rc28Key[] = ['transmit', 'f1', 'f2'];
const BACKOFF_MIN_MS = 1000;
const BACKOFF_MAX_MS = 10000;

export function parseRc28Message(raw: unknown): Rc28Message | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const msg = raw as Record<string, unknown>;
  if (msg.type === 'status' && typeof msg.connected === 'boolean' && typeof msg.available === 'boolean') {
    return { type: 'status', connected: msg.connected, available: msg.available };
  }
  if (msg.type === 'rotate' && Number.isSafeInteger(msg.ticks) && msg.ticks !== 0) {
    return { type: 'rotate', ticks: msg.ticks as number };
  }
  if (msg.type === 'key' && KEYS.includes(msg.key as Rc28Key) && typeof msg.pressed === 'boolean') {
    return { type: 'key', key: msg.key as Rc28Key, pressed: msg.pressed };
  }
  return null;
}

export function connectRc28(onMessage: (message: Rc28Message) => void): Rc28Connection {
  let ws: WebSocket | null = null;
  let closed = false;
  let backoff = BACKOFF_MIN_MS;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let leds: Rc28Leds | null = null;

  const sendLeds = () => {
    if (leds && ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ leds }));
  };

  const open = () => {
    if (closed) return;
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = authenticatedWsUrl(`${proto}//${location.host}/api/v1/rc28`);
    let protocols: string[];
    try {
      protocols = controllerClient.protocols();
    } catch {
      timer = setTimeout(open, BACKOFF_MAX_MS);
      return;
    }
    const socket = protocols.length ? new WebSocket(url, protocols) : new WebSocket(url);
    ws = socket;
    socket.onopen = () => {
      backoff = BACKOFF_MIN_MS;
      sendLeds();
    };
    socket.onmessage = (event) => {
      if (typeof event.data !== 'string') return;
      let parsed: unknown;
      try { parsed = JSON.parse(event.data); } catch { return; }
      const message = parseRc28Message(parsed);
      if (message) onMessage(message);
    };
    socket.onclose = () => {
      if (ws === socket) ws = null;
      onMessage({ type: 'status', connected: false, available: false });
      if (closed) return;
      timer = setTimeout(open, backoff);
      backoff = Math.min(backoff * 2, BACKOFF_MAX_MS);
    };
  };
  open();

  return {
    setLeds(next) {
      leds = next;
      sendLeds();
    },
    close() {
      closed = true;
      if (timer) clearTimeout(timer);
      ws?.close();
      ws = null;
    },
  };
}
