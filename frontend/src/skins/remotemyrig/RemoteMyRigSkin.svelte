<!--
  RemoteMyRig skin: the row layout registered under the `remotemyrig` layout
  manifest (`presentation/layouts/remotemyrig-declarations.ts`). Like
  `sdr-test`, it forwards the App's instrument composition to RadioLayout,
  which owns placement; RadioLayout's `remotemyrig` branch arranges the same
  semantic surfaces in rows instead of side columns.
-->
<script lang="ts">
  import type { InstrumentComposition } from '../../components-v2/wiring/instrument-composition';
  import RadioLayout from '../../components-v2/layout/RadioLayout.svelte';
  import '../desktop-v2/semantic-controls.css';
  import './remotemyrig.css';

  let { instruments }: { instruments: InstrumentComposition } = $props();
</script>

<RadioLayout skinId="remotemyrig" {instruments} />
