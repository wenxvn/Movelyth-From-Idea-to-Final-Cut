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
 * The image always fits inside its region box.  When Python computed a crop for the
 * target aspect (`layer.crop`), the image is drawn with that crop instead of `contain`:
 * the crop was verified to keep the subject, so it fills the frame without guessing.
 */
const cropStyle = (layer: Layer): React.CSSProperties => {
  const crop = layer.crop;
  if (!crop || crop.length !== 4 || !crop[2] || !crop[3]) {
    return {width: '100%', height: '100%', objectFit: 'contain'};
  }
  const [left, top, width, height] = crop;
  return {
    position: 'absolute',
    width: '100%',
    height: '100%',
    // Scale the source so the crop rectangle fills the box, then shift it into place.
    objectFit: 'cover',
    objectPosition: `${((left + width / 2) / Math.max(1, cropSource(layer)[0])) * 100}% ` +
      `${((top + height / 2) / Math.max(1, cropSource(layer)[1])) * 100}%`,
  };
};

const cropSource = (layer: Layer): [number, number] => {
  const source = layer.crop_source;
  if (!source || source.length < 2) return [1, 1];
  return [source[0], source[1]];
};

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
      <Img src={staticFile(name)} style={cropStyle(layer)}/>
      {layer.text && <div style={{position: 'absolute', bottom: 10, left: 12, color: '#fff4dd', fontSize: 20,
        background: '#07141cce', padding: '8px 14px', borderRadius: 8}}>{layer.text}</div>}
    </div>
  </div>;
};
