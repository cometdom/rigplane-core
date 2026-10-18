<script lang="ts">
  import { HardwareButton } from '$lib/Button';
  import { runtime } from '$lib/runtime';
  import { SSB_TX_BANDWIDTHS, setSsbTxBandwidth } from '$lib/runtime/ssb-tx-bandwidth';
  import { hasCapability } from '$lib/stores/capabilities.svelte';

  const current = $derived(runtime.state?.ssbTxBandwidth ?? null);
</script>

{#if hasCapability('ssb_tx_bw')}
  <div class="ssb-tx-bw" role="radiogroup" aria-label="TBW" data-testid="ssb-tx-bw">
    <span class="ssb-tx-bw-label">TBW</span>
    {#each SSB_TX_BANDWIDTHS as choice (choice.value)}
      <HardwareButton
        active={current === choice.value} role="radio" ariaChecked={current === choice.value}
        indicator="edge-left" color="cyan" onclick={() => setSsbTxBandwidth(choice.value)}
      >{choice.label}</HardwareButton>
    {/each}
  </div>
{/if}

<style>
  .ssb-tx-bw { display: flex; align-items: center; gap: 6px; padding: 4px 0; }
  .ssb-tx-bw-label { min-width: 3rem; font-size: 0.75rem; font-weight: 700; color: var(--v2-text-secondary); }
</style>
