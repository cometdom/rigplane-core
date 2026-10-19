/**
 * The operator's RX monitor choice (RADIO = the radio's own speaker, LIVE =
 * radio audio played on this computer), kept across sessions. LIVE when
 * nothing is stored: a remote station is heard through the computer.
 */
const KEY = 'rigplane.rx-monitor-mode';

export type RxMonitorPreference = 'live' | 'local';

function storage(): Storage | null {
  return typeof globalThis.localStorage?.getItem === 'function' ? globalThis.localStorage : null;
}

export function readRxMonitorPreference(): RxMonitorPreference {
  try {
    return storage()?.getItem(KEY) === 'local' ? 'local' : 'live';
  } catch {
    return 'live';
  }
}

/** Remember RADIO or LIVE; MUTE is a momentary choice and is not kept. */
export function rememberRxMonitorMode(mode: string): void {
  const value = mode === 'live' ? 'live' : mode === 'local' || mode === 'radio' ? 'local' : null;
  if (value === null) return;
  try { storage()?.setItem(KEY, value); } catch { /* storage unavailable */ }
}
