import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

const state: { current: { overflow?: boolean | null } | null } = { current: null };
vi.mock('$lib/runtime', () => ({ runtime: { get state() { return state.current; } } }));

const { default: OverflowIndicator } = await import('../OverflowIndicator.svelte');

let component: ReturnType<typeof mount> | null = null;
afterEach(() => { if (component) unmount(component); component = null; document.body.innerHTML = ''; });

function render() {
  component = mount(OverflowIndicator, { target: document.body });
  flushSync();
  return document.querySelector<HTMLElement>('[data-testid="overflow-indicator"]');
}

describe('OverflowIndicator', () => {
  it('is absent until the radio reports OVF', () => {
    state.current = { overflow: null };
    expect(render()).toBeNull();
  });

  it('is dark without overload and lit with it', () => {
    state.current = { overflow: false };
    expect(render()?.dataset.on).toBe('false');
    unmount(component!); component = null;
    state.current = { overflow: true };
    expect(render()?.dataset.on).toBe('true');
  });
});
