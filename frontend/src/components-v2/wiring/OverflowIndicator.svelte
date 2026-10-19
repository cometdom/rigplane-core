<!--
  Receiver overload (OVF) lamp: lit while the radio reports overload,
  dark otherwise, absent while the reading has never arrived.
-->
<script lang="ts">
  import { runtime } from '$lib/runtime';

  let overflow = $derived(runtime.state?.overflow);
</script>

{#if typeof overflow === 'boolean'}
  <span class="ovf" data-testid="overflow-indicator" data-on={overflow}
    role="status" aria-label={overflow ? 'OVF: overload' : 'OVF: no overload'}>OVF</span>
{/if}

<style>
  .ovf {
    display: inline-block;
    padding: 1px 6px;
    border: 1px solid var(--v2-border-darker, #333);
    border-radius: 3px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--v2-text-secondary, #6b7280);
  }
  .ovf[data-on='true'] {
    color: #fff;
    background: var(--v2-accent-red, #ef4444);
    border-color: var(--v2-accent-red, #ef4444);
  }
</style>
