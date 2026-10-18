<!--
  RemoteMyRig shell witness: the same `SemanticRadioSurfaces` children-snippet
  shape as `DesktopShellWitness.svelte`, mounting `RemoteMyRigSkin` instead of
  `DesktopSkin`, so the row layout renders over the fixture seams.
-->
<script lang="ts">
  import SemanticRadioSurfaces from '../src/components-v2/wiring/SemanticRadioSurfaces.svelte';
  import RemoteMyRigSkin from '../src/skins/remotemyrig/RemoteMyRigSkin.svelte';
</script>

<SemanticRadioSurfaces>
  {#snippet children(instruments)}
    <RemoteMyRigSkin {instruments} />
  {/snippet}
</SemanticRadioSurfaces>
