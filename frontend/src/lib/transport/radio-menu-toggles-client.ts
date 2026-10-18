import { getAuthHeaders } from './http-client';

/** One persistent on/off radio-menu item; `on` is null when the radio did not answer. */
export interface RadioMenuToggle {
  readonly name: string;
  readonly on: boolean | null;
}

const PATH = '/api/v1/radio/menu-toggles';

function toToggle(value: unknown): RadioMenuToggle {
  const v = value as Record<string, unknown> | null;
  if (typeof v !== 'object' || v === null || typeof v.name !== 'string'
    || (v.on !== null && typeof v.on !== 'boolean')) {
    throw new TypeError('Invalid radio menu toggle payload');
  }
  return { name: v.name, on: v.on as boolean | null };
}

async function readJson(response: Response): Promise<unknown> {
  if (!response.ok) throw new Error(`radio menu toggles: HTTP ${response.status}`);
  return response.json();
}

export async function loadRadioMenuToggles(): Promise<RadioMenuToggle[]> {
  const body = await readJson(await fetch(PATH, { headers: getAuthHeaders(), redirect: 'error' }));
  const toggles = (body as { toggles?: unknown }).toggles;
  if (!Array.isArray(toggles)) throw new TypeError('Invalid radio menu toggles payload');
  return toggles.map(toToggle);
}

export async function setRadioMenuToggle(name: string, on: boolean): Promise<RadioMenuToggle> {
  const response = await fetch(PATH, {
    method: 'PUT',
    headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
    redirect: 'error',
    body: JSON.stringify({ name, on }),
  });
  return toToggle(await readJson(response));
}
