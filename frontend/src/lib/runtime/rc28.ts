/**
 * ICOM RC-28 behaviour: wheel → VFO tuning in tuning-step units, F1/F2 →
 * configurable actions. The TRANSMIT key is handled where the on-screen PTT
 * is (components-v2/wiring), so it shares the PTT gate.
 */
import { getTuningStep } from '$lib/stores/tuning.svelte';
import { makeKeyboardHandlers } from './commands/panel-commands';

export {
  connectRc28,
  type Rc28Connection,
  type Rc28Key,
  type Rc28Leds,
  type Rc28Message,
} from '$lib/transport/rc28-client';

export type Rc28TransmitMode = 'toggle' | 'hold';
export type Rc28Function = 'ts_down' | 'ts_up' | 'none';

export interface Rc28Settings {
  transmitMode: Rc28TransmitMode;
  f1: Rc28Function;
  f2: Rc28Function;
  /** Wheel ticks per tuning step. */
  ticksPerStep: number;
}

export const RC28_DEFAULT_SETTINGS: Rc28Settings = {
  transmitMode: 'toggle',
  f1: 'ts_down',
  f2: 'ts_up',
  ticksPerStep: 1,
};

const STORAGE_KEY = 'rigplane.rc28';
const FUNCTIONS: readonly Rc28Function[] = ['ts_down', 'ts_up', 'none'];

function storage(): Storage | null {
  return typeof globalThis.localStorage?.getItem === 'function' ? globalThis.localStorage : null;
}

export function getRc28Settings(): Rc28Settings {
  let stored: Record<string, unknown> = {};
  try {
    const raw = storage()?.getItem(STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    if (typeof parsed === 'object' && parsed !== null) stored = parsed as Record<string, unknown>;
  } catch { /* unreadable storage keeps the defaults */ }
  const fn = (value: unknown, fallback: Rc28Function) =>
    FUNCTIONS.includes(value as Rc28Function) ? value as Rc28Function : fallback;
  const ticks = stored.ticksPerStep;
  return {
    transmitMode: stored.transmitMode === 'hold' ? 'hold' : RC28_DEFAULT_SETTINGS.transmitMode,
    f1: fn(stored.f1, RC28_DEFAULT_SETTINGS.f1),
    f2: fn(stored.f2, RC28_DEFAULT_SETTINGS.f2),
    ticksPerStep: Number.isSafeInteger(ticks) && (ticks as number) >= 1 && (ticks as number) <= 16
      ? ticks as number : RC28_DEFAULT_SETTINGS.ticksPerStep,
  };
}

export function runRc28Function(fn: Rc28Function): void {
  if (fn === 'none') return;
  makeKeyboardHandlers().dispatch({
    action: 'adjust_tuning_step', params: { direction: fn === 'ts_down' ? 'down' : 'up' },
  });
}

export interface Rc28Tuner {
  rotate(ticks: number): void;
  dispose(): void;
}

/**
 * Accumulates wheel ticks and sends at most one tune per `flushMs`, so a
 * fast spin (an RC-28 report every ~10 ms) becomes a few larger steps
 * instead of a command per report computed from a stale frequency.
 */
export function createRc28Tuner(ticksPerStep: number, flushMs = 40): Rc28Tuner {
  let pendingTicks = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const flush = () => {
    timer = null;
    const steps = Math.trunc(pendingTicks / ticksPerStep);
    if (steps === 0) return;
    pendingTicks -= steps * ticksPerStep;
    const step = getTuningStep();
    if (!Number.isSafeInteger(step) || step <= 0) return;
    makeKeyboardHandlers().dispatch({ action: 'tune', params: { deltaHz: steps * step } });
  };
  return {
    rotate(ticks) {
      if (Math.sign(ticks) !== Math.sign(pendingTicks)) pendingTicks = 0;
      pendingTicks += ticks;
      timer ??= setTimeout(flush, flushMs);
    },
    dispose() {
      if (timer) clearTimeout(timer);
      timer = null;
      pendingTicks = 0;
    },
  };
}
