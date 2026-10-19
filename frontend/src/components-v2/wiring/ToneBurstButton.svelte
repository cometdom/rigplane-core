<!--
  1750 Hz repeater access tone (FM). The tone lasts while the key is held
  (at least TONE_BURST_MIN_MS, at most TONE_BURST_MAX_MS). From receive it
  keys through the managed TX controller with the on-screen PTT gate and
  releases after the tone; inside the operator's own latched transmit it
  only sends the tone.
-->
<script lang="ts">
  import { onDestroy } from 'svelte';
  import { HardwareButton } from '$lib/Button';
  import { runtime } from '$lib/runtime';
  import { activeReceiverOrNull } from '$lib/runtime/adapters/pending-intent-table';
  import { getManagedAppTxController } from '$lib/runtime/tx-controller/managed-app-host';
  import {
    sendTxTone, stopTxTone, toneBurstPlan,
    TONE_BURST_HZ, TONE_BURST_MAX_MS, TONE_BURST_MIN_MS, TONE_BURST_TAIL_MS,
  } from '$lib/runtime/tx-tone';

  const tx = getManagedAppTxController();
  let busy = $state(false);
  let held = $state(false);
  let alive = true;
  onDestroy(() => { alive = false; held = false; });

  let fm = $derived.by(() => {
    const state = runtime.state;
    const receiver = activeReceiverOrNull(state);
    const rx = receiver === 1 ? state?.sub : receiver === 0 ? state?.main : null;
    return rx?.mode === 'FM';
  });

  const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

  async function waitFor(check: () => boolean, timeoutMs: number): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;
    while (alive && Date.now() < deadline) {
      if (check()) return true;
      await sleep(50);
    }
    return check();
  }

  async function burst(): Promise<void> {
    if (busy || !fm || runtime.remoteController) return;
    const plan = toneBurstPlan(tx.snapshot());
    if (plan === 'refused') return;
    busy = true;
    try {
      if (plan === 'key-first') {
        tx.transmitOn();
        if (!await waitFor(() => tx.snapshot().phase === 'active', 3000)) {
          await tx.forceOff();
          return;
        }
      }
      await sendTxTone(TONE_BURST_HZ, TONE_BURST_MAX_MS);
      const started = Date.now();
      await sleep(TONE_BURST_MIN_MS);
      await waitFor(() => !held, TONE_BURST_MAX_MS - (Date.now() - started));
      await stopTxTone().catch(() => undefined);
      await sleep(TONE_BURST_TAIL_MS);
    } catch {
      await stopTxTone().catch(() => undefined);
    } finally {
      if (plan === 'key-first') await tx.forceOff();
      busy = false;
    }
  }

  function press(event: PointerEvent): void {
    if (event.button !== 0) return;
    held = true;
    void burst();
  }
  function release(): void { held = false; }
  /** Keyboard activation (Enter/Space) sends the minimum burst. */
  function keyboard(event: MouseEvent): void {
    if (event.detail === 0) { held = false; void burst(); }
  }
</script>

<div class="tone-burst">
  <HardwareButton active={busy} disabled={!fm || (busy && !held)} indicator="edge-left" color="cyan"
    title="1750 Hz" onpointerdown={press} onpointerup={release} onclick={keyboard}>1750</HardwareButton>
</div>
<svelte:window onpointerup={release} onblur={release} />

<style>
  .tone-burst { display: flex; padding: 2px 8px; }
</style>
