<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '$lib/i18n';
  import {
    loadRadioMenuToggles, setRadioMenuToggle, type RadioMenuToggle,
  } from '$lib/runtime/radio-menu-toggles';

  const LABEL_KEYS: Record<string, string> = {
    ext_preamp_144: 'core.settings.radioMenu.extPreamp144',
    ext_preamp_430: 'core.settings.radioMenu.extPreamp430',
    ext_preamp_1200: 'core.settings.radioMenu.extPreamp1200',
  };

  let toggles = $state<RadioMenuToggle[] | null>(null);
  let failed = $state<'load' | 'write' | null>(null);
  let busy = $state<string | null>(null);

  const label = (name: string): string => (LABEL_KEYS[name] ? t(LABEL_KEYS[name]) : name);

  onMount(() => {
    loadRadioMenuToggles()
      .then((list) => { toggles = list; })
      .catch(() => { failed = 'load'; });
  });

  async function change(name: string, on: boolean): Promise<void> {
    busy = name;
    failed = null;
    try {
      const updated = await setRadioMenuToggle(name, on);
      toggles = (toggles ?? []).map((item) => (item.name === updated.name ? updated : item));
    } catch {
      failed = 'write';
    } finally {
      busy = null;
    }
  }
</script>

<div class="radio-menu">
  {#if failed === 'load'}
    <p class="radio-menu-note" data-testid="radio-menu-error">{t('core.settings.radioMenu.loadError')}</p>
  {:else if toggles !== null && toggles.length === 0}
    <p class="radio-menu-note" data-testid="radio-menu-empty">{t('core.settings.radioMenu.empty')}</p>
  {:else if toggles !== null}
    {#each toggles as item (item.name)}
      <label class="radio-menu-row">
        <input
          type="checkbox"
          data-testid={`radio-menu-toggle-${item.name}`}
          checked={item.on === true}
          disabled={item.on === null || busy !== null}
          onchange={(event) => change(item.name, event.currentTarget.checked)}
        />
        <span>{label(item.name)}</span>
      </label>
    {/each}
    {#if failed === 'write'}
      <p class="radio-menu-note" data-testid="radio-menu-error">{t('core.settings.radioMenu.writeError')}</p>
    {/if}
  {/if}
</div>

<style>
  .radio-menu { display: flex; flex-direction: column; gap: 6px; }
  .radio-menu-row { display: flex; align-items: center; gap: 8px; cursor: pointer; }
  .radio-menu-note { margin: 0; font-size: 0.85em; opacity: 0.8; }
</style>
