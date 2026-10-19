<!--
  Puts the RX monitor back on the operator's remembered choice (LIVE by
  default) once per page session, after the radio reports audio. Renders
  nothing.
-->
<script module lang="ts">
  let restored = false;
</script>

<script lang="ts">
  import { runtime } from '$lib/runtime';
  import { restoreRxMonitorMode } from '$lib/runtime/adapters/panel-adapters';

  $effect(() => {
    if (restored || runtime.caps?.audio !== true) return;
    restored = true;
    restoreRxMonitorMode();
  });
</script>
