<!--
  1750 Hz repeater access tone (FM). Keys through the managed TX controller
  with the on-screen PTT gate, sends the tone for one second, then releases;
  inside the operator's own latched transmit it only sends the tone.
-->
<script lang="ts">
  import { onDestroy } from 'svelte';
  import { HardwareButton } from '$lib/Button';
  import { runtime } from '$lib/runtime';
  import { activeReceiverOrNull } from '$lib/runtime/adapters/pending-intent-table';
  import { getManagedAppTxController } from '$lib/runtime/tx-controller/managed-app-host';
  import { sendTxTone, toneBurstPlan, TONE_BURST_HZ, TONE_BURST_MS } from '$lib/runtime/tx-tone';

  const tx = getManagedAppTxController();
  let busy = $state(false);

  let fm = $derived.by(() => {
    const state = runtime.state;
    const receiver = activeReceiverOrNull(state);
    const rx = receiver === 1 ? state?.sub : receiver === 0 ? state?.main : null;
    return rx?.mode === 'FM';
  });

  const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
  let alive = true;
  onDestroy(() => { alive = false; });

  async function waitForActive(timeoutMs: number): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;
    while (alive && Date.now() < deadline) {
      if (tx.snapshot().phase === 'active') return true;
      await sleep(50);
    }
    return false;
  }

  async function burst(): Promise<void> {
    if (busy || !fm || runtime.remoteController) return;
    const plan = toneBurstPlan(tx.snapshot());
    if (plan === 'refused') return;
    busy = true;
    try {
      if (plan === 'key-first') {
        tx.transmitOn();
        if (!await waitForActive(3000)) { await tx.forceOff(); return; }
        await sleep(150);
      }
      await sendTxTone(TONE_BURST_HZ, TONE_BURST_MS).catch(() => undefined);
      await sleep(TONE_BURST_MS + 100);
      if (plan === 'key-first') await tx.forceOff();
    } finally {
      busy = false;
    }
  }
</script>

<div class="tone-burst">
  <HardwareButton active={busy} disabled={!fm || busy} indicator="edge-left" color="cyan"
    title="1750 Hz" onclick={burst}>1750</HardwareButton>
</div>

<style>
  .tone-burst { display: flex; padding: 2px 8px; }
</style>
