import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import type {MovieProps} from './types';
import {SceneStage} from './Stage';
import {captionBand, fitFont, footerBand, headingBand, labelBand, safeMargin} from './layouts';
import {accent, clamp, themeFor} from './theme';

const sceneAt = (scenes: MovieProps['scenes'], frame: number) => {
  let offset = 0;
  for (let i = 0; i < scenes.length; i++) {
    if (frame < offset + scenes[i].frames) return {scene: scenes[i], index: i, local: frame - offset};
    offset += scenes[i].frames;
  }
  const last = scenes[scenes.length - 1];
  return {scene: last, index: scenes.length - 1, local: last.frames - 1};
};

const captionSize = (text: string, vertical: boolean): number => {
  const base = vertical ? 44 : 39;
  if (text.length > 34) return Math.round(base * 0.74);
  if (text.length > 24) return Math.round(base * 0.86);
  return base;
};

const isIllustrative = (scene: MovieProps['scenes'][number]): boolean =>
  scene.layers.some((layer) => layer.type === 'diagram') ||
  scene.layers.some((layer) => layer.type === 'procedural' && ['network', 'wave', 'orbit'].includes(layer.procedural)) ||
  scene.layers.some((layer) => layer.type === 'chart' && layer.source_note.length > 0);

export const Movie: React.FC<MovieProps> = (props) => {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const vertical = height > width;
  const theme = themeFor(props.style);
  const scenes = props.scenes;
  const {scene, index, local} = sceneAt(scenes, frame);
  const layout = props.cover ? 'diagram' : scene.layout;
  const progress = props.cover ? 0.62 : clamp(local / Math.max(1, scene.frames - 1));
  const accentColor = accent[scene.color] || accent.cyan;
  const fade = props.cover ? 1 : Math.min(1, local / 12, (scene.frames - local) / 10);
  const caption = props.cover ? undefined :
    scene.captions.find((page) => local / fps >= page.start && local / fps < page.end);
  const heading = props.cover ? props.title : scene.heading;
  const margin = safeMargin(vertical);
  const band = captionBand(vertical);
  const footer = footerBand(vertical);
  const headingBox = headingBand(vertical, layout);
  const labelBox = labelBand(vertical, layout);
  const headingBase = props.cover ? (vertical ? 82 : 75) : (vertical ? 62 : 58);
  const headingSize = fitFont(heading, headingBox, headingBase, vertical ? 38 : 34, 1.3);
  const labels = props.cover ? [] : scene.labels;
  const labelSize = fitFont(labels.join(''), labelBox, vertical ? 26 : 27, 19, 1.5);
  const tagline = theme.name === 'documentary' ? '知识的现场 · 逐帧解释'
    : theme.name === 'minimal' ? '从一个问题开始' : 'FROM IDEA TO FINAL CUT.';
  return <AbsoluteFill style={{background: theme.background, color: theme.text, fontFamily: theme.fontFamily}}>
    <AbsoluteFill style={{background: theme.overlay}}/>
    <div style={{position: 'absolute', inset: 0, opacity: theme.name === 'minimal' ? 0.06 : 0.13,
      backgroundImage: `linear-gradient(${theme.grid}20 1px, transparent 1px), linear-gradient(90deg, ${theme.grid}20 1px, transparent 1px)`,
      backgroundSize: '70px 70px'}}/>
    <div style={{position: 'absolute', top: vertical ? 88 : 45, left: vertical ? 70 : 85, fontSize: vertical ? 28 : 23,
      letterSpacing: 3, color: theme.muted}}>MOVELYTH <span style={{color: accentColor}}>幕绎</span></div>
    <div style={{position: 'absolute', top: vertical ? 92 : 48, right: vertical ? 88 : 85, fontSize: 20, color: theme.muted}}>
      {props.episode}
    </div>
    <div style={{position: 'absolute', left: headingBox.x, top: headingBox.y, width: headingBox.w, height: headingBox.h,
      opacity: Math.max(0, fade), display: 'flex', flexDirection: 'column', justifyContent: 'flex-start',
      translate: `0px ${props.cover ? 0 : 14 * (1 - Math.min(1, local / 18))}px`}}>
      <div style={{width: 65, height: 5, borderRadius: 5, background: accentColor, marginBottom: vertical ? 24 : 20,
        flexShrink: 0}}/>
      <div style={{fontSize: headingSize, lineHeight: 1.3, fontWeight: theme.headingWeight,
        letterSpacing: theme.letterSpacing, overflowWrap: 'anywhere', wordBreak: 'break-word'}}>{heading}</div>
      <div style={{fontSize: vertical ? 23 : 20, letterSpacing: 3, color: theme.muted, marginTop: vertical ? 20 : 14,
        flexShrink: 0}}>
        {props.cover ? tagline : `CHAPTER ${String(index + 1).padStart(2, '0')} / ${String(scenes.length).padStart(2, '0')}`}
      </div>
    </div>
    <AbsoluteFill style={{opacity: Math.max(0, fade)}}>
      <SceneStage scene={scene} time={props.cover ? 4 : local / fps} progress={progress}
        layers={props.layers} vertical={vertical} theme={theme}/>
    </AbsoluteFill>
    {labels.length > 0 && <div style={{position: 'absolute', left: labelBox.x, top: labelBox.y,
      width: labelBox.w, height: labelBox.h, display: 'flex', gap: 12,
      flexDirection: vertical ? 'row' : 'column', flexWrap: 'wrap', alignContent: 'flex-start',
      opacity: Math.max(0, fade)}}>
      {labels.map((label, i) => <div key={label} style={{fontSize: labelSize,
        color: i === 0 ? accentColor : theme.muted,
        borderLeft: `3px solid ${accentColor}${i === 0 ? '' : '55'}`, padding: '6px 16px',
        background: `${theme.surface}bb`, maxWidth: '100%', overflowWrap: 'anywhere'}}>{label}</div>)}
    </div>}
    {!props.cover && caption && <div style={{position: 'absolute', left: margin + 40, right: margin + 40,
      top: band.top, height: band.bottom - band.top, display: 'flex', justifyContent: 'center', alignItems: 'center'}}>
      <div style={{fontSize: captionSize(caption.text, vertical), fontWeight: 500, lineHeight: 1.45, textAlign: 'center',
        background: '#05111de8', borderRadius: 16, padding: '13px 24px', maxWidth: '100%', overflowWrap: 'anywhere',
        boxShadow: '0 4px 24px #0008'}}>{caption.text}</div>
    </div>}
    <div style={{position: 'absolute', left: margin + 5, right: margin + 5, top: footer.top,
      fontSize: vertical ? 19 : 18, lineHeight: 1.5, color: theme.muted}}>
      {props.cover ? (theme.name === 'documentary' ? '数学与科学 · 看见结构的力量' : 'Movelyth · 幕绎')
        : `来源：${(props.sources[scene.source_index]?.label || '原理演示').slice(0, 65)}${isIllustrative(scene) ? ' · 原理示意' : ''}`}
    </div>
    <div style={{position: 'absolute', bottom: 0, left: 0, height: 4,
      width: `${(index + progress) / scenes.length * 100}%`, background: accentColor}}/>
  </AbsoluteFill>;
};
