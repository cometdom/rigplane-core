import { describe, expect, it } from 'vitest';
import { parseRc28Message } from '../rc28-client';

describe('parseRc28Message', () => {
  it('accepts the three server message shapes', () => {
    expect(parseRc28Message({ type: 'status', connected: true, available: true }))
      .toEqual({ type: 'status', connected: true, available: true });
    expect(parseRc28Message({ type: 'rotate', ticks: -3 })).toEqual({ type: 'rotate', ticks: -3 });
    expect(parseRc28Message({ type: 'key', key: 'f2', pressed: false }))
      .toEqual({ type: 'key', key: 'f2', pressed: false });
  });

  it('rejects malformed messages', () => {
    expect(parseRc28Message({ type: 'rotate', ticks: 1.5 })).toBeNull();
    expect(parseRc28Message({ type: 'rotate', ticks: 0 })).toBeNull();
    expect(parseRc28Message({ type: 'key', key: 'f3', pressed: true })).toBeNull();
    expect(parseRc28Message(null)).toBeNull();
  });
});
