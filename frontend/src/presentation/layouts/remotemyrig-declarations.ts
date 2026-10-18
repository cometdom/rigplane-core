/**
 * RemoteMyRig layout manifest: the same one-surface zones as `desktop-v2`
 * (`desktop-declarations.ts`), so every semantic surface has a host and the
 * legacy sidebar twins retire through the same `declared` channel. Only the
 * geometry differs, and it lives in RadioLayout's `remotemyrig` branch.
 */
import { registerLayout, type LayoutManifest } from './contract';

export const remoteMyRigLayout: LayoutManifest = {
  schemaVersion: 1,
  id: 'remotemyrig',
  displayName: 'RemoteMyRig',
  zones: [
    { id: 'receiver-deck', surfaces: ['vfo'] },
    { id: 'rx-tx', surfaces: ['rxTx'] },
    { id: 'tx-aux', surfaces: ['txAux'] },
    { id: 'meters', surfaces: ['meters'] },
    { id: 'scope-display', surfaces: ['scopeDisplay'] },
    { id: 'filter', surfaces: ['filter'] },
    { id: 'rf-front-end', surfaces: ['rfFrontEnd'] },
    { id: 'band', surfaces: ['band'] },
    { id: 'antenna', surfaces: ['antenna'] },
    { id: 'rit-xit-scan', surfaces: ['ritXitScan'] },
    { id: 'repeater', surfaces: ['repeater'] },
    { id: 'rx-audio', surfaces: ['rxAudio'] },
    { id: 'dsp', surfaces: ['dsp'] },
    { id: 'cw-keyer', surfaces: ['cwKeyer'] },
    { id: 'memory', surfaces: ['memory'] },
    { id: 'scope-controls', surfaces: ['scopeControls'] },
  ],
  compatibleTopologies: ['1/single', '1/ab', '2/ab_shared', '2/main_sub'],
  requiredSemanticSurfaces: ['vfo', 'rxTx'],
  stageSizing: { mode: 'fluid', responsiveBreakpoints: [] },
  fallbackLayoutId: null,
};

registerLayout(remoteMyRigLayout);
