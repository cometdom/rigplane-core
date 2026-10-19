<!--
  ICOM RC-28 wiring: wheel → VFO tuning, F1/F2 → their configured actions,
  TRANSMIT → `onTransmit` (the owner applies the on-screen PTT gate), and
  the four LEDs from live state. Renders nothing.
-->
<script lang="ts">
  import { onDestroy } from 'svelte';
  import { runtime } from '$lib/runtime';
  import {
    connectRc28, createRc28Tuner, getRc28Settings, runRc28Function,
    type Rc28Message, type Rc28TransmitMode,
  } from '$lib/runtime/rc28';

  interface Props {
    onTransmit: (pressed: boolean, mode: Rc28TransmitMode) => void;
    txLit: boolean;
  }
  let { onTransmit, txLit }: Props = $props();

  const settings = getRc28Settings();
  const tuner = createRc28Tuner(settings.ticksPerStep);
  let f1Down = $state(false);
  let f2Down = $state(false);

  function handle(message: Rc28Message): void {
    if (message.type === 'rotate') {
      tuner.rotate(message.ticks);
    } else if (message.type === 'key') {
      if (message.key === 'transmit') {
        onTransmit(message.pressed, settings.transmitMode);
      } else {
        if (message.key === 'f1') f1Down = message.pressed;
        else f2Down = message.pressed;
        if (message.pressed) runRc28Function(settings[message.key]);
      }
    }
  }

  const connection = connectRc28(handle);
  let link = $derived(
    runtime.state?.connection?.controlConnected === true && runtime.state.connection.radioReady === true,
  );
  $effect(() => {
    connection.setLeds({ tx: txLit, f1: f1Down, f2: f2Down, link });
  });
  onDestroy(() => {
    connection.close();
    tuner.dispose();
  });
</script>
