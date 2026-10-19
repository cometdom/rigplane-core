import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const dispatch = vi.fn();
vi.mock('../commands/panel-commands', () => ({ makeKeyboardHandlers: () => ({ dispatch }) }));
vi.mock('$lib/stores/tuning.svelte', () => ({ getTuningStep: () => 1000 }));

const { createRc28Tuner, getRc28Settings, runRc28Function, RC28_DEFAULT_SETTINGS } = await import('../rc28');

describe('RC-28 wheel', () => {
  beforeEach(() => { dispatch.mockReset(); vi.useFakeTimers(); });
  afterEach(() => vi.useRealTimers());

  it('coalesces ticks into one tune of steps × tuning step', () => {
    const tuner = createRc28Tuner(1);
    tuner.rotate(3);
    tuner.rotate(2);
    vi.advanceTimersByTime(40);
    expect(dispatch).toHaveBeenCalledTimes(1);
    expect(dispatch).toHaveBeenCalledWith({ action: 'tune', params: { deltaHz: 5000 } });
  });

  it('keeps the remainder below one step and tunes down counter-clockwise', () => {
    const tuner = createRc28Tuner(4);
    tuner.rotate(-9);
    vi.advanceTimersByTime(40);
    expect(dispatch).toHaveBeenCalledWith({ action: 'tune', params: { deltaHz: -2000 } });
    tuner.rotate(-3);
    vi.advanceTimersByTime(40);
    expect(dispatch).toHaveBeenLastCalledWith({ action: 'tune', params: { deltaHz: -1000 } });
  });

  it('a direction change drops the opposite remainder', () => {
    const tuner = createRc28Tuner(4);
    tuner.rotate(3);
    tuner.rotate(-1);
    vi.advanceTimersByTime(40);
    expect(dispatch).not.toHaveBeenCalled();
  });
});

describe('RC-28 keys and settings', () => {
  beforeEach(() => { dispatch.mockReset(); localStorage.clear(); });

  it('F1/F2 defaults are TS− and TS+ with TRANSMIT as a toggle', () => {
    expect(getRc28Settings()).toEqual(RC28_DEFAULT_SETTINGS);
    expect(RC28_DEFAULT_SETTINGS).toMatchObject({ f1: 'ts_down', f2: 'ts_up', transmitMode: 'toggle' });
  });

  it('runs the tuning-step action', () => {
    runRc28Function('ts_down');
    expect(dispatch).toHaveBeenCalledWith({ action: 'adjust_tuning_step', params: { direction: 'down' } });
    runRc28Function('none');
    expect(dispatch).toHaveBeenCalledTimes(1);
  });

  it('reads stored settings and rejects invalid values', () => {
    localStorage.setItem('rigplane.rc28', JSON.stringify({ transmitMode: 'hold', f1: 'bogus', ticksPerStep: 99 }));
    expect(getRc28Settings()).toEqual({ ...RC28_DEFAULT_SETTINGS, transmitMode: 'hold' });
  });
});
