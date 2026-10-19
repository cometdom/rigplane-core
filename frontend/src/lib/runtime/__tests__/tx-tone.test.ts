import { describe, expect, it } from 'vitest';
import { toneBurstPlan } from '../tx-tone';

describe('toneBurstPlan', () => {
  it('sends the tone inside the operator latched transmit', () => {
    expect(toneBurstPlan({ fresh: true, phase: 'active', intent: 'latched' })).toBe('in-transmit');
  });
  it('keys first from a fresh idle state, like the on-screen PTT', () => {
    expect(toneBurstPlan({ fresh: true, phase: 'idle', intent: null })).toBe('key-first');
  });
  it('refuses stale or busy states', () => {
    expect(toneBurstPlan({ fresh: false, phase: 'idle', intent: null })).toBe('refused');
    expect(toneBurstPlan({ fresh: true, phase: 'releasing', intent: null })).toBe('refused');
    expect(toneBurstPlan({ fresh: true, phase: 'active', intent: 'momentary' })).toBe('refused');
  });
});
