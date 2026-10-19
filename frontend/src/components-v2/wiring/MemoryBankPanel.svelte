<!--
  Local memory banks (Icom CSV imports kept on this computer): pick a bank,
  click a channel to tune the radio to it. The radio's own memories are not
  touched.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '$lib/i18n';
  import {
    applyMemoryChannel, deleteMemoryBank, formatChannelMhz, importMemoryBank, loadMemoryBanks,
    type MemoryBank, type MemoryBankChannel,
  } from '$lib/runtime/memory-bank';

  const DUP_LABEL = { off: '', minus: 'DUP−', plus: 'DUP+' } as const;
  const SELECTED_KEY = 'rigplane.memory-bank.selected';

  let banks = $state<MemoryBank[]>([]);
  let selected = $state('');
  let message = $state('');
  let lastChannel = $state<number | null>(null);
  let fileInput: HTMLInputElement | undefined = $state();

  let bank = $derived(banks.find((b) => b.name === selected) ?? banks[0] ?? null);

  async function refresh(): Promise<void> {
    try {
      banks = await loadMemoryBanks();
      if (!banks.some((b) => b.name === selected)) selected = banks[0]?.name ?? '';
    } catch (error) {
      message = String(error instanceof Error ? error.message : error);
    }
  }

  onMount(() => {
    try { selected = localStorage.getItem(SELECTED_KEY) ?? ''; } catch { /* storage off */ }
    void refresh();
  });

  function select(name: string): void {
    selected = name;
    try { localStorage.setItem(SELECTED_KEY, name); } catch { /* storage off */ }
  }

  /** Icom software writes ANSI (Windows-1252); a UTF-8 file decodes cleanly first. */
  async function readText(file: File): Promise<string> {
    const bytes = await file.arrayBuffer();
    try { return new TextDecoder('utf-8', { fatal: true }).decode(bytes); } catch {
      return new TextDecoder('windows-1252').decode(bytes);
    }
  }

  async function importFiles(files: FileList | null): Promise<void> {
    if (!files) return;
    let last = '';
    for (const file of Array.from(files)) {
      const name = file.name.replace(/\.csv$/i, '');
      try {
        const count = await importMemoryBank(name, await readText(file));
        message = t('core.memoryBank.imported', { count });
        last = name;
      } catch (error) {
        message = `${file.name}: ${error instanceof Error ? error.message : String(error)}`;
      }
    }
    if (fileInput) fileInput.value = '';
    await refresh();
    if (last) select(last);
  }

  async function removeBank(): Promise<void> {
    if (!bank || !confirm(t('core.memoryBank.deleteConfirm', { name: bank.name }))) return;
    await deleteMemoryBank(bank.name).catch(() => undefined);
    await refresh();
  }

  async function recall(channel: MemoryBankChannel): Promise<void> {
    const result = await applyMemoryChannel(channel);
    if (result === 'transmitting') message = t('core.memoryBank.transmitting');
    else if (result === 'applied') { lastChannel = channel.ch; message = ''; }
  }

  function toneLabel(channel: MemoryBankChannel): string {
    if (channel.tone === 'tone' && channel.toneCentiHz !== null) return `T ${channel.toneCentiHz / 100}`;
    if (channel.tone === 'tsql' && channel.tsqlCentiHz !== null) return `TSQL ${channel.tsqlCentiHz / 100}`;
    return channel.tone === 'dtcs' ? 'DTCS' : '';
  }
</script>

<section class="memory-bank" data-testid="memory-bank">
  <div class="bar">
    {#if banks.length > 0}
      <label>{t('core.memoryBank.bank')}
        <select value={bank?.name ?? ''} onchange={(e) => select(e.currentTarget.value)}>
          {#each banks as b (b.name)}<option value={b.name}>{b.name}</option>{/each}
        </select>
      </label>
    {/if}
    <button type="button" onclick={() => fileInput?.click()}>{t('core.memoryBank.import')}</button>
    {#if bank}<button type="button" class="danger" onclick={removeBank}>{t('core.memoryBank.delete')}</button>{/if}
    <input bind:this={fileInput} type="file" accept=".csv,text/csv" multiple hidden
      onchange={(e) => importFiles(e.currentTarget.files)} />
    {#if message}<span class="message" role="status">{message}</span>{/if}
  </div>

  {#if !bank}
    <p class="empty">{t('core.memoryBank.empty')}</p>
  {:else}
    <table>
      <thead><tr>
        <th>CH</th><th>{t('core.memoryBank.colName')}</th><th>MHz</th><th>Mode</th><th>Dup</th><th>{t('core.memoryBank.colTone')}</th>
      </tr></thead>
      <tbody>
        {#each bank.channels as channel (channel.ch)}
          <tr class:current={lastChannel === channel.ch} data-testid={`memory-bank-ch-${channel.ch}`}
            tabindex="0" onclick={() => recall(channel)}
            onkeydown={(e) => { if (e.key === 'Enter') void recall(channel); }}>
            <td>{String(channel.ch).padStart(2, '0')}</td>
            <td>{channel.name}</td>
            <td class="freq">{formatChannelMhz(channel.freqHz)}</td>
            <td>{channel.mode}{channel.data ? '-D' : ''}</td>
            <td>{DUP_LABEL[channel.dup]}{channel.dup !== 'off' && channel.offsetHz !== null ? ` ${channel.offsetHz / 1_000_000}` : ''}</td>
            <td>{toneLabel(channel)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>

<style>
  .memory-bank { display: flex; flex-direction: column; gap: 6px; font-size: 13px; }
  .bar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  label { display: flex; align-items: center; gap: 6px; color: var(--v2-text-secondary, #9aa); }
  select, button {
    padding: 4px 10px; font: inherit; color: var(--v2-text-primary, inherit);
    background: var(--v2-bg-card, #141b27); border: 1px solid var(--v2-border-darker, #333); border-radius: 4px;
  }
  button { cursor: pointer; }
  button.danger { color: var(--v2-accent-red, #ef4444); }
  .message { color: var(--v2-text-secondary, #9aa); }
  .empty { margin: 0; color: var(--v2-text-secondary, #9aa); }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-weight: 600; color: var(--v2-text-secondary, #9aa); padding: 2px 8px; }
  td { padding: 3px 8px; border-top: 1px solid var(--v2-border-dark, #222); white-space: nowrap; }
  td.freq { font-variant-numeric: tabular-nums; }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: color-mix(in srgb, var(--v2-accent-cyan, #00d4ff) 12%, transparent); }
  tbody tr.current { color: var(--v2-accent-cyan, #00d4ff); }
</style>
