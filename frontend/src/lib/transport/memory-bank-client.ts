import { getAuthHeaders } from './http-client';

/** One channel of an imported Icom memory CSV (server `web/memory_bank.py`). */
export interface MemoryBankChannel {
  readonly ch: number;
  readonly name: string;
  readonly freqHz: number;
  readonly mode: string;
  readonly data: boolean;
  readonly filter: number | null;
  readonly dup: 'off' | 'minus' | 'plus';
  readonly offsetHz: number | null;
  readonly tone: 'off' | 'tone' | 'tsql' | 'dtcs';
  readonly toneCentiHz: number | null;
  readonly tsqlCentiHz: number | null;
}

export interface MemoryBank {
  readonly name: string;
  readonly channels: readonly MemoryBankChannel[];
}

const BANKS = '/api/v1/memory-banks';
const DUPLEX_OFFSET = '/api/v1/radio/duplex-offset';

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

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const numOrNull = (v: unknown): number | null => (isNum(v) ? v : null);

function toChannel(value: unknown): MemoryBankChannel | null {
  const v = value as Record<string, unknown> | null;
  if (typeof v !== 'object' || v === null || !isNum(v.ch) || !isNum(v.freqHz)
    || typeof v.mode !== 'string') return null;
  return {
    ch: v.ch,
    name: typeof v.name === 'string' ? v.name : '',
    freqHz: v.freqHz,
    mode: v.mode,
    data: v.data === true,
    filter: numOrNull(v.filter),
    dup: v.dup === 'minus' || v.dup === 'plus' ? v.dup : 'off',
    offsetHz: numOrNull(v.offsetHz),
    tone: v.tone === 'tone' || v.tone === 'tsql' || v.tone === 'dtcs' ? v.tone : 'off',
    toneCentiHz: numOrNull(v.toneCentiHz),
    tsqlCentiHz: numOrNull(v.tsqlCentiHz),
  };
}

export async function loadMemoryBanks(): Promise<MemoryBank[]> {
  const banks = (await send(BANKS, 'GET') as { banks?: unknown }).banks;
  if (!Array.isArray(banks)) throw new TypeError('Invalid memory bank payload');
  return banks.flatMap((bank: unknown) => {
    const b = bank as { name?: unknown; channels?: unknown } | null;
    if (!b || typeof b.name !== 'string' || !Array.isArray(b.channels)) return [];
    return [{
      name: b.name,
      channels: b.channels.map(toChannel).filter((c): c is MemoryBankChannel => c !== null),
    }];
  });
}

export async function importMemoryBank(name: string, csv: string): Promise<number> {
  const result = await send(BANKS, 'POST', { name, csv }) as { count?: unknown };
  return isNum(result.count) ? result.count : 0;
}

export async function deleteMemoryBank(name: string): Promise<void> {
  await send(`${BANKS}/delete`, 'POST', { name });
}

export async function setDuplexOffset(hz: number): Promise<void> {
  await send(DUPLEX_OFFSET, 'PUT', { hz });
}
