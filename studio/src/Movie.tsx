import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import type {MovieProps} from './types';
import {Visual, palette} from './Visual';

export const Movie: React.FC<MovieProps> = (props) => {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const vertical = height > width;
  let offset = 0, index = props.scenes.length - 1;
  for (let i = 0; i < props.scenes.length; i++) {
    if (frame < offset + props.scenes[i].frames || props.cover) {index = i; break;}
    offset += props.scenes[i].frames;
  }
  const scene = props.scenes[index];
  const local = frame - offset;
  const progress = props.cover ? 0.62 : local / Math.max(1, scene.frames - 1);
  const accent = palette[scene.color];
  const fade = props.cover ? 1 : Math.min(1, local / 12, (scene.frames - local) / 10);
  const caption = scene.captions.find(c => local / fps >= c.start && local / fps < c.end);
  const heading = props.cover ? props.title : scene.heading;
  return <AbsoluteFill style={{background: '#07151f', color: '#f0eedf', fontFamily: '"Microsoft YaHei", "Noto Sans CJK SC", sans-serif'}}>
    <AbsoluteFill style={{background: 'radial-gradient(ellipse at 80% 35%, #1e394433, transparent 65%), linear-gradient(145deg, #0f2736, #07151f 60%)'}}/>
    <div style={{position: 'absolute', inset: 0, opacity: 0.13, backgroundImage: 'linear-gradient(#8db1bc20 1px, transparent 1px), linear-gradient(90deg, #8db1bc20 1px, transparent 1px)', backgroundSize: '70px 70px'}}/>
    <div style={{position: 'absolute', top: vertical ? 88 : 45, left: vertical ? 70 : 85, fontSize: vertical ? 28 : 23, letterSpacing: 3, color: '#a1bbc3'}}>MOVELYTH <span style={{color: accent}}>幕绎</span></div>
    <div style={{position: 'absolute', top: vertical ? 92 : 48, right: vertical ? 88 : 85, fontSize: 20, color: '#86a0ac'}}>{props.episode}</div>
    <div style={{position: 'absolute', top: vertical ? 175 : 170, left: vertical ? 70 : 85, width: vertical ? 900 : 640, opacity: Math.max(0, fade), translate: `0px ${props.cover ? 0 : 14 * (1 - Math.min(1, local / 18))}px`}}>
      <div style={{width: 65, height: 5, borderRadius: 5, background: accent, marginBottom: 27}}/>
      <div style={{fontSize: props.cover ? (vertical ? 82 : 75) : (vertical ? 75 : 65), lineHeight: 1.35, fontWeight: 700, letterSpacing: 1, overflowWrap: 'anywhere'}}>{heading}</div>
      <div style={{fontSize: vertical ? 23 : 20, letterSpacing: 3, color: '#86a0ac', marginTop: 22}}>{props.cover ? 'FROM IDEA TO FINAL CUT.' : `CHAPTER ${String(index + 1).padStart(2, '0')} / ${String(props.scenes.length).padStart(2, '0')}`}</div>
    </div>
    <div style={{position: 'absolute', left: vertical ? 45 : 790, top: vertical ? 490 : 175, width: vertical ? 990 : 1060, height: vertical ? 810 : 680, opacity: Math.max(0, fade)}}>
      <Visual scene={scene} time={props.cover ? 4 : local / fps} progress={progress} layers={props.layers}/>
    </div>
    <div style={{position: 'absolute', top: vertical ? 1320 : 550, left: vertical ? 80 : 85, width: vertical ? 870 : 620, display: 'flex', gap: 13, flexDirection: vertical ? 'row' : 'column', flexWrap: 'wrap', opacity: Math.max(0, fade)}}>
      {scene.labels.map((label, i) => <div key={label} style={{fontSize: vertical ? 25 : 26, color: i === 0 ? accent : '#adbdc1', borderLeft: `3px solid ${accent}${i === 0 ? '' : '55'}`, padding: '7px 17px', background: '#0b2230bb', maxWidth: '100%', overflowWrap: 'anywhere'}}>{label}</div>)}
    </div>
    {!props.cover && caption && <div style={{position: 'absolute', left: vertical ? 78 : 120, right: vertical ? 125 : 120, bottom: vertical ? 245 : 95, display: 'flex', justifyContent: 'center'}}>
      <div style={{fontSize: vertical ? 44 : 39, fontWeight: 500, lineHeight: 1.6, textAlign: 'center', background: '#05111de8', borderRadius: 16, padding: '13px 24px', maxWidth: '100%', overflowWrap: 'anywhere', boxShadow: '0 4px 24px #0008'}}>{caption.text}</div>
    </div>}
    <div style={{position: 'absolute', left: vertical ? 75 : 85, right: vertical ? 135 : 85, bottom: vertical ? 155 : 35, fontSize: vertical ? 19 : 18, lineHeight: 1.5, color: '#6f919e'}}>
      {props.cover ? '数学与科学 · 看见结构的力量' : `来源：${(props.sources[scene.source_index]?.label || '原理演示').slice(0, 65)}${['network', 'wave'].includes(scene.visual) ? ' · 原理示意' : ''}`}
    </div>
    <div style={{position: 'absolute', bottom: 0, left: 0, height: 4, width: `${(index + progress) / props.scenes.length * 100}%`, background: accent}}/>
  </AbsoluteFill>;
};
