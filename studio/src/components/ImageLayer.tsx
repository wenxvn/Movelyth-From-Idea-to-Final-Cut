import React from 'react';
import {Img, staticFile} from 'remotion';
import type {Layer} from '../types';
import type {Theme} from '../theme';
import {accent} from '../theme';

export const resolveAsset = (layer: Layer, layers: string[]): string | undefined => {
  if (!layer.data_ref) return undefined;
  const dashed = layer.data_ref.replace(/_/g, '-');
  const candidates = [dashed, `asset-${layer.data_ref}`];
  return layers.find((name) => candidates.some((prefix) => name.startsWith(prefix)));
};

/**
 * The image always fits inside its region box: `objectFit: contain` plus a
 * max-height keeps a wide photo from overflowing into the caption band.
 */
export const ImageLayer: React.FC<{layer: Layer; theme: Theme; layers: string[]; reveal: number}> =
({layer, theme, layers, reveal}) => {
  const name = resolveAsset(layer, layers);
  const color = accent[layer.color] || theme.text;
  if (!name) {
    return <div style={{color: theme.muted, fontSize: 24, border: `2px dashed ${theme.muted}66`, padding: 20}}>
      素材 {layer.data_ref} 不可用，未使用远程替代图
    </div>;
  }
  return <div style={{position: 'relative', width: '100%', height: '100%', display: 'flex',
    alignItems: 'center', justifyContent: 'center', opacity: reveal}}>
    <div style={{position: 'relative', width: '100%', height: '100%', maxHeight: '100%',
      borderRadius: theme.radius, overflow: 'hidden', border: `2px solid ${color}66`,
      boxShadow: `0 18px 60px ${color}16`, background: theme.surface}}>
      <Img src={staticFile(name)} style={{width: '100%', height: '100%', objectFit: 'contain'}}/>
      {layer.text && <div style={{position: 'absolute', bottom: 10, left: 12, color: '#fff4dd', fontSize: 20,
        background: '#07141cce', padding: '8px 14px', borderRadius: 8}}>{layer.text}</div>}
    </div>
  </div>;
};
