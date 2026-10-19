import { beforeEach, describe, expect, it } from 'vitest';
import { readRxMonitorPreference, rememberRxMonitorMode } from '../rx-monitor-preference';

describe('RX monitor preference', () => {
  beforeEach(() => localStorage.clear());

  it('starts on LIVE when nothing is stored', () => {
    expect(readRxMonitorPreference()).toBe('live');
  });

  it('keeps RADIO and LIVE, ignores MUTE', () => {
    rememberRxMonitorMode('local');
    expect(readRxMonitorPreference()).toBe('local');
    rememberRxMonitorMode('mute');
    expect(readRxMonitorPreference()).toBe('local');
    rememberRxMonitorMode('live');
    expect(readRxMonitorPreference()).toBe('live');
  });
});
