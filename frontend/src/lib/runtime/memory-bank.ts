/**
 * Local memory banks (Icom CSV imports kept by the server, never written to
 * the radio). `applyMemoryChannel` tunes the active receiver to a channel
 * with the ordinary radio intents; the duplex offset goes through its own
 * HTTP route.
 */
import { setDuplexOffset, type MemoryBankChannel } from '$lib/transport/memory-bank-client';
import { dispatchRadioIntent } from './commands/radio-intents';
import { makeVfoHandlers } from './commands/panel-commands';
import { activeReceiverOrNull } from './adapters/pending-intent-table';
import { runtime } from './frontend-runtime';

export {
  deleteMemoryBank,
  importMemoryBank,
  loadMemoryBanks,
  type MemoryBank,
  type MemoryBankChannel,
} from '$lib/transport/memory-bank-client';

/** RepeaterShiftDirection wire codes (core/types.py). */
const SHIFT_DIRECTION = { off: 0, plus: 1, minus: 2 } as const;
/** Modes that accept DATA (the IC-9700 front panel offers DATA in these). */
const DATA_MODES = new Set(['USB', 'LSB', 'AM', 'FM']);

export type ApplyResult = 'applied' | 'transmitting' | 'no-radio';

export async function applyMemoryChannel(ch: MemoryBankChannel): Promise<ApplyResult> {
  const state = runtime.state;
  const caps = runtime.caps;
  const receiver = activeReceiverOrNull(state);
  if (!state || !caps || receiver === null) return 'no-radio';
  if (state.ptt === true) return 'transmitting';
  const has = (tag: string) => caps.capabilities.includes(tag);

  if (caps.modes.includes(ch.mode)) {
    dispatchRadioIntent(ch.filter !== null
      ? { name: 'set_mode', params: { mode: ch.mode, filter: ch.filter, receiver } }
      : { name: 'set_mode', params: { mode: ch.mode, receiver } });
    if (has('data_mode') && DATA_MODES.has(ch.mode)) {
      dispatchRadioIntent({ name: 'set_data_mode', params: { mode: ch.data ? 1 : 0, receiver } });
    }
  }
  makeVfoHandlers().onFreqChange(ch.freqHz, receiver, 'jump');

  if (has('repeater_shift')) {
    dispatchRadioIntent({
      name: 'set_repeater_shift', params: { direction: SHIFT_DIRECTION[ch.dup], receiver },
    });
  }
  if (has('repeater_tone')) {
    const tone = ch.tone === 'tone';
    const tsql = ch.tone === 'tsql';
    dispatchRadioIntent({ name: 'set_repeater_tsql', params: { on: tsql, receiver } });
    dispatchRadioIntent({ name: 'set_repeater_tone', params: { on: tone, receiver } });
    if (tone && ch.toneCentiHz !== null) {
      dispatchRadioIntent({ name: 'set_tone_freq', params: { freq: ch.toneCentiHz, receiver } });
    }
    if (tsql && ch.tsqlCentiHz !== null) {
      dispatchRadioIntent({ name: 'set_tsql_freq', params: { freq: ch.tsqlCentiHz, receiver } });
    }
  }
  if (ch.dup !== 'off' && ch.offsetHz !== null) {
    await setDuplexOffset(ch.offsetHz).catch(() => undefined);
  }
  return 'applied';
}

/** `144,300000`-style display in MHz, the way CS-9700 shows it. */
export function formatChannelMhz(hz: number): string {
  return (hz / 1_000_000).toFixed(4);
}
