import { beforeEach, describe, expect, it, vi } from 'vitest';

const dispatch = vi.fn();
const onFreqChange = vi.fn();
const setDuplexOffset = vi.fn().mockResolvedValue(undefined);
const state: { current: Record<string, unknown> | null } = { current: null };
const caps: { current: Record<string, unknown> | null } = { current: null };

vi.mock('../commands/radio-intents', () => ({ dispatchRadioIntent: dispatch }));
vi.mock('../commands/panel-commands', () => ({ makeVfoHandlers: () => ({ onFreqChange }) }));
vi.mock('../frontend-runtime', () => ({
  runtime: { get state() { return state.current; }, get caps() { return caps.current; } },
}));
vi.mock('$lib/transport/memory-bank-client', () => ({ setDuplexOffset }));

const { applyMemoryChannel } = await import('../memory-bank');

const repeater = {
  ch: 30, name: 'FRU 12', freqHz: 430_300_000, mode: 'FM', data: false, filter: 1,
  dup: 'plus', offsetHz: 1_600_000, tone: 'tone', toneCentiHz: 12300, tsqlCentiHz: 6700,
} as const;

describe('applyMemoryChannel', () => {
  beforeEach(() => {
    dispatch.mockReset(); onFreqChange.mockReset(); setDuplexOffset.mockClear();
    state.current = { ptt: false, active: 'MAIN' };
    caps.current = {
      modes: ['USB', 'LSB', 'CW', 'FM'],
      capabilities: ['data_mode', 'repeater_shift', 'repeater_tone'],
    };
  });

  it('sets mode, data, frequency, shift, offset and tone for a repeater', async () => {
    await expect(applyMemoryChannel(repeater)).resolves.toBe('applied');
    expect(dispatch.mock.calls.map(([intent]) => intent)).toEqual([
      { name: 'set_mode', params: { mode: 'FM', filter: 1, receiver: 0 } },
      { name: 'set_data_mode', params: { mode: 0, receiver: 0 } },
      { name: 'set_repeater_shift', params: { direction: 1, receiver: 0 } },
      { name: 'set_repeater_tsql', params: { on: false, receiver: 0 } },
      { name: 'set_repeater_tone', params: { on: true, receiver: 0 } },
      { name: 'set_tone_freq', params: { freq: 12300, receiver: 0 } },
    ]);
    expect(onFreqChange).toHaveBeenCalledWith(430_300_000, 0, 'jump');
    expect(setDuplexOffset).toHaveBeenCalledWith(1_600_000);
  });

  it('tunes the SUB receiver when it is active, and skips the offset on simplex', async () => {
    state.current = { ptt: false, active: 'SUB' };
    await applyMemoryChannel({ ...repeater, dup: 'off', tone: 'off', mode: 'CW' });
    expect(onFreqChange).toHaveBeenCalledWith(430_300_000, 1, 'jump');
    expect(dispatch.mock.calls.some(([i]) => i.name === 'set_data_mode')).toBe(false);
    expect(setDuplexOffset).not.toHaveBeenCalled();
  });

  it('does nothing while transmitting', async () => {
    state.current = { ptt: true, active: 'MAIN' };
    await expect(applyMemoryChannel(repeater)).resolves.toBe('transmitting');
    expect(dispatch).not.toHaveBeenCalled();
    expect(onFreqChange).not.toHaveBeenCalled();
  });
});
