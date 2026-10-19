<!--
  CI-V over virtual COM ports: com0com pairs and the ports rigplane opens
  for programs that need a dedicated CI-V port (OpsLog, OmniRig, …).
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '$lib/i18n';
  import {
    createCom0comPair, loadCivBridges, saveCivBridges,
    type CivBridge, type CivBridgeSettings,
  } from '$lib/runtime/civ-bridges';

  let settings = $state<CivBridgeSettings | null>(null);
  let error = $state('');
  let busy = $state(false);
  let pairA = $state('COM10');
  let pairB = $state('COM11');
  let addPort = $state('');

  async function run(action: () => Promise<CivBridgeSettings>): Promise<void> {
    busy = true;
    error = '';
    try {
      settings = await action();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }

  onMount(() => { void run(loadCivBridges); });

  function save(bridges: CivBridge[]): void {
    void run(() => saveCivBridges(bridges));
  }
  function update(port: string, patch: Partial<CivBridge>): void {
    save((settings?.bridges ?? []).map((b) => (b.port === port ? { ...b, ...patch } : b)));
  }
  function add(port: string): void {
    if (!port || settings?.bridges.some((b) => b.port === port)) return;
    save([...(settings?.bridges ?? []), { port, enabled: true, allowTx: false }]);
    addPort = '';
  }
  function remove(port: string): void {
    save((settings?.bridges ?? []).filter((b) => b.port !== port));
  }
  const inUse = (port: string) => settings?.bridges.some((b) => b.port === port) ?? false;
  function statusLabel(status: string | undefined): string {
    if (status === 'running') return t('core.civBridge.statusRunning');
    if (status?.startsWith('error: ')) return t('core.civBridge.statusError', { detail: status.slice(7) });
    return t('core.civBridge.statusStopped');
  }
</script>

<div class="civ-bridges" data-testid="civ-bridges">
  <p class="note">{t('core.civBridge.intro')}</p>

  {#if settings}
    <section>
      <h4>{t('core.civBridge.bridges')}</h4>
      {#if settings.bridges.length === 0}
        <p class="note">{t('core.civBridge.none')}</p>
      {:else}
        <div class="grid bridges">
          {#each settings.bridges as bridge (bridge.port)}
            <span class="port" data-testid={`civ-bridge-${bridge.port}`}>{bridge.port}</span>
            <span class="status" data-state={bridge.status}>{statusLabel(bridge.status)}</span>
            <label><input type="checkbox" checked={bridge.enabled} disabled={busy}
              onchange={(e) => update(bridge.port, { enabled: e.currentTarget.checked })} />
              {t('core.civBridge.enabled')}</label>
            <label><input type="checkbox" checked={bridge.allowTx} disabled={busy}
              onchange={(e) => update(bridge.port, { allowTx: e.currentTarget.checked })} />
              {t('core.civBridge.allowTx')}</label>
            <button type="button" disabled={busy} onclick={() => remove(bridge.port)}>{t('core.civBridge.remove')}</button>
          {/each}
        </div>
      {/if}
      <div class="row">
        <select bind:value={addPort} aria-label="COM">
          <option value=""></option>
          {#each settings.ports as port (port.device)}
            {#if !inUse(port.device)}<option value={port.device}>{port.device} — {port.description}</option>{/if}
          {/each}
        </select>
        <button type="button" disabled={busy || !addPort} onclick={() => add(addPort)}>{t('core.civBridge.add')}</button>
      </div>
    </section>

    <section>
      <h4>{t('core.civBridge.pairs')}</h4>
      {#if !settings.com0com}
        <p class="note">{t('core.civBridge.noCom0com')}</p>
      {:else}
        {#if settings.pairs.length > 0}
          <div class="grid pairs">
            {#each settings.pairs as pair (pair.a + pair.b)}
              <span class="port">{pair.a} ↔ {pair.b}</span>
              {#if !inUse(pair.a) && !inUse(pair.b)}
                <button type="button" disabled={busy} onclick={() => add(pair.b)}>
                  {t('core.civBridge.useFor', { port: pair.b })}
                </button>
              {:else}
                <span class="note">{t('core.civBridge.programUses', { port: inUse(pair.b) ? pair.a : pair.b })}</span>
              {/if}
            {/each}
          </div>
        {/if}
        <div class="row">
          <input aria-label="COM A" bind:value={pairA} size="6" />
          <span>↔</span>
          <input aria-label="COM B" bind:value={pairB} size="6" />
          <button type="button" disabled={busy} onclick={() => run(() => createCom0comPair(pairA.trim(), pairB.trim()))}>
            {t('core.civBridge.createPair')}
          </button>
        </div>
        <p class="note">{t('core.civBridge.createHint')}</p>
      {/if}
    </section>
  {/if}
  {#if error}<p class="note error" role="alert">{error}</p>{/if}
</div>

<style>
  .civ-bridges { display: flex; flex-direction: column; gap: 12px; padding: 6px 4px; font-size: 12px; }
  section { display: flex; flex-direction: column; gap: 8px; }
  h4 {
    margin: 0; font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--v2-text-secondary, #9aa);
  }
  .grid { display: grid; align-items: center; gap: 6px 14px; }
  .grid.bridges { grid-template-columns: max-content max-content max-content 1fr max-content; }
  .grid.pairs { grid-template-columns: max-content 1fr; }
  .row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .port { font-weight: 700; font-variant-numeric: tabular-nums; }
  .note { margin: 0; line-height: 1.4; color: var(--v2-text-secondary, #9aa); }
  .error { color: var(--v2-accent-red, #ef4444); }
  .status { color: var(--v2-text-secondary, #9aa); }
  .status[data-state='running'] { color: var(--v2-accent-green, #22c55e); }
  label { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
  input:not([type='checkbox']), select, button {
    padding: 4px 8px; font: inherit; color: var(--v2-text-primary, inherit);
    background: var(--v2-bg-card, #141b27); border: 1px solid var(--v2-border-darker, #333); border-radius: 4px;
  }
  select { min-width: 16rem; }
  button { cursor: pointer; }
  button:disabled { opacity: 0.5; cursor: default; }
</style>
