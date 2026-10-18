import { beforeEach, describe, expect, it, vi } from 'vitest';

const dispatch = vi.fn();
vi.mock('../commands/radio-intents', () => ({ dispatchRadioIntent: dispatch }));

const { setSsbTxBandwidth } = await import('../ssb-tx-bandwidth');

describe('setSsbTxBandwidth', () => {
  beforeEach(() => dispatch.mockReset());

  it('dispatches set_ssb_tx_bw with the preset value', () => {
    setSsbTxBandwidth(2);
    expect(dispatch).toHaveBeenCalledWith({ name: 'set_ssb_tx_bw', params: { value: 2 } });
  });

  it('ignores a value outside WIDE / MID / NAR', () => {
    setSsbTxBandwidth(3);
    expect(dispatch).not.toHaveBeenCalled();
  });
});
