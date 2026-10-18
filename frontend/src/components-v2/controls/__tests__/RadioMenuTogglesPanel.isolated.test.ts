import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';

const api = vi.hoisted(() => ({ load: vi.fn(), set: vi.fn() }));
vi.mock('$lib/runtime/radio-menu-toggles', () => ({
  loadRadioMenuToggles: api.load,
  setRadioMenuToggle: api.set,
}));

import RadioMenuTogglesPanel from '../RadioMenuTogglesPanel.svelte';

let component: ReturnType<typeof mount> | null = null;

function mountPanel(): HTMLElement {
  const target = document.createElement('div');
  document.body.appendChild(target);
  component = mount(RadioMenuTogglesPanel, { target });
  flushSync();
  return target;
}

const box = (target: HTMLElement, name: string): HTMLInputElement | null =>
  target.querySelector<HTMLInputElement>(`[data-testid="radio-menu-toggle-${name}"]`);

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
  api.load.mockReset();
  api.set.mockReset();
});

describe('radio menu toggles panel', () => {
  it('shows one labelled switch per toggle with the value the radio reported', async () => {
    api.load.mockResolvedValue([
      { name: 'ext_preamp_144', on: true },
      { name: 'ext_preamp_430', on: false },
    ]);
    const target = mountPanel();
    await vi.waitFor(() => expect(box(target, 'ext_preamp_144')).not.toBeNull());
    expect(box(target, 'ext_preamp_144')!.checked).toBe(true);
    expect(box(target, 'ext_preamp_430')!.checked).toBe(false);
    expect(target.textContent).toContain('External P.AMP 144 MHz');
  });

  it('writes a change and shows the value the radio read back', async () => {
    api.load.mockResolvedValue([{ name: 'ext_preamp_430', on: false }]);
    api.set.mockResolvedValue({ name: 'ext_preamp_430', on: true });
    const target = mountPanel();
    await vi.waitFor(() => expect(box(target, 'ext_preamp_430')).not.toBeNull());
    box(target, 'ext_preamp_430')!.click();
    await vi.waitFor(() => expect(api.set).toHaveBeenCalledWith('ext_preamp_430', true));
    await vi.waitFor(() => expect(box(target, 'ext_preamp_430')!.checked).toBe(true));
  });

  it('says so when the radio has no menu toggles', async () => {
    api.load.mockResolvedValue([]);
    const target = mountPanel();
    await vi.waitFor(() =>
      expect(target.querySelector('[data-testid="radio-menu-empty"]')).not.toBeNull());
  });

  it('reports a failed read', async () => {
    api.load.mockRejectedValue(new Error('503'));
    const target = mountPanel();
    await vi.waitFor(() =>
      expect(target.querySelector('[data-testid="radio-menu-error"]')).not.toBeNull());
  });
});
