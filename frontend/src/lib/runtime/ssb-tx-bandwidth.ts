import { dispatchRadioIntent } from './commands/radio-intents';

/** SSB TX bandwidth presets, in the radio's own order (CI-V 16 58). */
export const SSB_TX_BANDWIDTHS = [
  { value: 0, label: 'WIDE' },
  { value: 1, label: 'MID' },
  { value: 2, label: 'NAR' },
] as const;

export function setSsbTxBandwidth(value: number): void {
  if (!SSB_TX_BANDWIDTHS.some((choice) => choice.value === value)) return;
  dispatchRadioIntent({ name: 'set_ssb_tx_bw', params: { value } });
}
