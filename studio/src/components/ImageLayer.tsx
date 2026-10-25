import React from 'react';
import {Img, staticFile} from 'remotion';
import type {Layer} from '../types';
import type {Theme} from '../theme';
import {accent} from '../theme';

export const resolveAsset = (layer: Layer, layers: string[]): string | undefined => {
  if (!layer.data_ref) return undefined;
  const dashed = layer.data_ref.replace(/_/g, '-');
  return layers.find((name) => name.startsWith(dashed) || name.replace(/-/g, '_').startsWith(layer.data_ref));
};

export const ImageLayer: React.FC<{layer: Layer; theme: Theme; layers: string[]; reveal: number}> =
({layer, theme, layers, reveal}) => {
  const name = resolveAsset(layer, layers);
  const color = accent[layer.color] || theme.text;
  if (!name) {
    return <div style={{color: theme.muted, fontSize: 26, border: `2px dashed ${theme.muted}66`, padding: 24}}>
      素材 {layer.data_ref} 不可用，未使用远程替代图
    </div>;
  }
  return <div style={{position: 'relative', width: '100%', height: '100%', display: 'flex', alignItems: 'center', opacity: reveal}}>
    <div style={{position: 'relative', width: '100%', aspectRatio: '1.6', borderRadius: theme.radius, overflow: 'hidden',
      border: `2px solid ${color}66`, boxShadow: `0 25px 100px ${color}16`}}>
      <Img src={staticFile(name)} style={{position: 'absolute', width: '100%', height: '100%', objectFit: 'cover'}}/>
      {layer.text && <div style={{position: 'absolute', bottom: 14, left: 18, color: '#fff4dd', fontSize: 22,
        background: '#07141cce', padding: '10px 16px', borderRadius: 10}}>{layer.text}</div>}
    </div>
  </div>;
};
