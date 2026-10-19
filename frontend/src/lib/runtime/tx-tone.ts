/**
 * Repeater access tone burst (1750 Hz). The tone rides the browser TX audio
 * path, so it needs a transmit keyed through the on-screen PTT gate.
 */
export { sendTxTone } from '$lib/transport/tx-tone-client';

export const TONE_BURST_HZ = 1750;
export const TONE_BURST_MS = 1000;

interface TxSnapshot {
  readonly fresh: boolean;
  readonly phase: string;
  readonly intent: 'momentary' | 'latched' | null;
}

/**
 * `in-transmit`: the operator's own latched transmit is on — send the tone
 * and stay in TX. `key-first`: key with the on-screen PTT gate (fresh and
 * idle), send the tone, then release. `refused`: anything else.
 */
export function toneBurstPlan(tx: TxSnapshot): 'in-transmit' | 'key-first' | 'refused' {
  if (tx.intent === 'latched' && tx.phase === 'active') return 'in-transmit';
  if (tx.fresh && tx.phase === 'idle') return 'key-first';
  return 'refused';
}
