import { afterEach, describe, expect, it } from 'vitest';
import { setLocale, t, tPlural } from '../index';

afterEach(() => {
  setLocale('en-US');
});

describe('fr-FR catalog', () => {
  it('resolves French text once selected, keeping glossary tokens and placeholders', () => {
    setLocale('fr-FR');
    expect(t('core.settings.title')).toBe('RÉGLAGES');
    expect(t('core.settings.radioMenu.extPreamp430')).toBe('Préampli externe 430 MHz');
    expect(t('core.rxTx.fault.code', { code: 'uncertain' })).toBe('Défaut TX : uncertain');
  });

  it('uses the French plural rule (1 is singular)', () => {
    setLocale('fr-FR');
    expect(tPlural('core.diagnostics.attachedFiles', 1)).toBe('1 fichier joint');
    expect(tPlural('core.diagnostics.attachedFiles', 3)).toBe('3 fichiers joints');
  });
});
