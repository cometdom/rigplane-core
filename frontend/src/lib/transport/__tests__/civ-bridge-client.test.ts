import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadCivBridges, saveCivBridges } from '../civ-bridge-client';

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
afterEach(() => vi.unstubAllGlobals());

describe('civ bridge client', () => {
  it('normalises the settings payload', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({
      bridges: [{ port: 'COM11', enabled: true, allowTx: false, status: 'running' }, { nope: 1 }],
      com0com: true,
    })));
    const settings = await loadCivBridges();
    expect(settings.bridges).toHaveLength(1);
    expect(settings).toMatchObject({ com0com: true, ports: [], pairs: [] });
  });

  it('PUTs only port, enabled and allowTx', async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok({ bridges: [] }));
    vi.stubGlobal('fetch', fetchMock);
    await saveCivBridges([{ port: 'COM11', enabled: true, allowTx: true, status: 'running' }]);
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body)).toEqual({ bridges: [{ port: 'COM11', enabled: true, allowTx: true }] });
  });

  it('surfaces the server error text', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"error":"local_only"}', { status: 403 })));
    await expect(loadCivBridges()).rejects.toThrow('local_only');
  });
});
