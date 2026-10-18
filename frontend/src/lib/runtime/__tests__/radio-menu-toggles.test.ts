import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadRadioMenuToggles, setRadioMenuToggle } from '../radio-menu-toggles';

const okJson = (body: unknown): Response =>
  new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('radio menu toggles client', () => {
  it('reads the toggle list', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okJson({
      toggles: [{ name: 'ext_preamp_144', on: true }, { name: 'ext_preamp_430', on: null }],
    }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(loadRadioMenuToggles()).resolves.toEqual([
      { name: 'ext_preamp_144', on: true },
      { name: 'ext_preamp_430', on: null },
    ]);
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/radio/menu-toggles');
  });

  it('writes one toggle with PUT and returns the read-back', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okJson({ name: 'ext_preamp_430', on: true }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(setRadioMenuToggle('ext_preamp_430', true))
      .resolves.toEqual({ name: 'ext_preamp_430', on: true });
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe('/api/v1/radio/menu-toggles');
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body)).toEqual({ name: 'ext_preamp_430', on: true });
  });

  it('rejects an error status and a malformed body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 502 })));
    await expect(setRadioMenuToggle('ext_preamp_144', true)).rejects.toThrow();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okJson({ toggles: [{ name: 1 }] })));
    await expect(loadRadioMenuToggles()).rejects.toThrow();
  });
});
