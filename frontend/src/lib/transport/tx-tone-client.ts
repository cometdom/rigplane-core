import { getAuthHeaders } from './http-client';

/** Ask the server to replace browser TX audio with a tone burst. */
export async function sendTxTone(hz: number, ms: number): Promise<void> {
  const response = await fetch('/api/v1/tx-tone', {
    method: 'POST',
    headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
    redirect: 'error',
    body: JSON.stringify({ hz, ms }),
  });
  if (!response.ok) throw new Error(`tx tone: HTTP ${response.status}`);
}

/** End a tone burst before its time is up. */
export async function stopTxTone(): Promise<void> {
  const response = await fetch('/api/v1/tx-tone', {
    method: 'POST',
    headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
    redirect: 'error',
    body: JSON.stringify({ stop: true }),
  });
  if (!response.ok) throw new Error(`tx tone: HTTP ${response.status}`);
}
