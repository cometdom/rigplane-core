import { getAuthHeaders } from './http-client';

/** One CI-V COM bridge (server `web/civ_com_bridge.py`). */
export interface CivBridge {
  readonly port: string;
  readonly enabled: boolean;
  readonly allowTx: boolean;
  readonly status?: string;
}

export interface CivBridgeSettings {
  readonly bridges: readonly CivBridge[];
  readonly ports: readonly { device: string; description: string }[];
  readonly com0com: boolean;
  readonly pairs: readonly { a: string; b: string }[];
}

async function send(path: string, method: string, body?: unknown): Promise<unknown> {
  const response = await fetch(path, {
    method,
    headers: body === undefined
      ? getAuthHeaders()
      : { ...getAuthHeaders(), 'Content-Type': 'application/json' },
    redirect: 'error',
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const payload: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = (payload as { error?: unknown }).error;
    throw new Error(typeof error === 'string' ? error : `HTTP ${response.status}`);
  }
  return payload;
}

function toSettings(value: unknown): CivBridgeSettings {
  const v = value as Partial<Record<keyof CivBridgeSettings, unknown>>;
  const list = <T>(x: unknown): T[] => (Array.isArray(x) ? (x as T[]) : []);
  return {
    bridges: list<CivBridge>(v.bridges).filter((b) => typeof b?.port === 'string'),
    ports: list<{ device: string; description: string }>(v.ports),
    com0com: v.com0com === true,
    pairs: list<{ a: string; b: string }>(v.pairs),
  };
}

export async function loadCivBridges(): Promise<CivBridgeSettings> {
  return toSettings(await send('/api/v1/civ-bridges', 'GET'));
}

export async function saveCivBridges(bridges: readonly CivBridge[]): Promise<CivBridgeSettings> {
  const plain = bridges.map(({ port, enabled, allowTx }) => ({ port, enabled, allowTx }));
  return toSettings(await send('/api/v1/civ-bridges', 'PUT', { bridges: plain }));
}

export async function createCom0comPair(a: string, b: string): Promise<CivBridgeSettings> {
  return toSettings(await send('/api/v1/com0com/pairs', 'POST', { a, b }));
}
