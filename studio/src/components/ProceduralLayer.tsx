import React from 'react';
import {Img, staticFile} from 'remotion';
import type {Layer, Scene} from '../types';
import {accent, clamp, ease} from '../theme';
import type {Box} from '../Stage';

const px = (x: number) => 500 + x * 95;
const py = (y: number) => 320 - y * 95;

/**
 * Width of the drawing when the region is much wider than the 1000×640 canvas.
 *
 * A procedural drawing scaled to the region height leaves a large empty band on
 * both sides of a full-width "immersive" frame.  Filling the width entirely would
 * crop the drawing's labels, so it is enlarged by at most 1.4× and centred: the
 * content reads bigger and the crop stays inside the empty margins.
 */
const svgWidth = (box?: Box): string => {
  if (!box || box.h <= 0) return '100%';
  const natural = (box.h * 1000) / 640;
  const target = Math.min(box.w, natural * 1.4);
  return `${Math.max(natural, target)}px`;
};

/** The original seven procedural animations, now one layer type among others. */
export const ProceduralLayer: React.FC<{
  layer: Layer; scene: Scene; time: number; progress: number; reveal: number; layers: string[];
  box?: Box;
}> = ({layer, scene, time, progress, reveal, layers, box}) => {
  const kind = layer.procedural || scene.visual;
  const color = accent[layer.color] || '#68e5ed';
  const p = ease(progress);
  const textStyle = {fill: '#e9eedf', fontFamily: 'inherit', fontSize: 34};

  /**
   * A vector or projection drawn from real coefficients can occupy a tiny corner of
   * the 1000×640 canvas (a unit vector is 95 px).  Fitting the viewBox to the
   * content keeps the arrow readable at any scale without changing the data.
   */
  const zoomedViewBox = (points: [number, number][], pad = 150): string => {
    const xs = points.map(([x]) => x);
    const ys = points.map(([, y]) => y);
    const spanX = Math.max(...xs) - Math.min(...xs);
    const spanY = Math.max(...ys) - Math.min(...ys);
    // Padding proportional to the drawing: a fixed 150 px margin around a 140 px
    // vector left it looking like a dot in the middle of the frame.
    const margin = Math.min(pad, Math.max(46, Math.max(spanX, spanY) * 0.55));
    const minX = Math.min(...xs) - margin;
    const maxX = Math.max(...xs) + margin;
    const minY = Math.min(...ys) - margin;
    const maxY = Math.max(...ys) + margin;
    const aspect = box && box.h > 0 ? Math.max(0.9, Math.min(2.6, box.w / box.h)) : 1000 / 640;
    let w = Math.max(240, maxX - minX);
    let h = Math.max(170, maxY - minY);
    if (w / h > aspect) h = w / aspect;
    else w = h * aspect;
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    return `${cx - w / 2} ${cy - h / 2} ${w} ${h}`;
  };

  const vectorValues = layer.series[0]?.values;
  const directionValues = layer.series[1]?.values;
  let viewBox = '0 0 1000 640';
  if (kind === 'vectors' && vectorValues && vectorValues.length >= 2) {
    const [a, b] = vectorValues;
    viewBox = zoomedViewBox([[px(0), py(0)], [px(a), py(0)], [px(a), py(b)]], 150);
  } else if (kind === 'projection' && vectorValues && vectorValues.length >= 2) {
    const [x, y] = vectorValues;
    const ux = directionValues && directionValues.length >= 2 ? directionValues[0] : 1;
    const uy = directionValues && directionValues.length >= 2 ? directionValues[1] : 0.5;
    const factor = (x * ux + y * uy) / (ux * ux + uy * uy);
    viewBox = zoomedViewBox([[px(0), py(0)], [px(x), py(y)], [px(factor * ux), py(factor * uy)]], 160);
  }
  // Caption anchor: the top-left corner of the *visible* area, so a zoomed-in
  // vector keeps its formula on screen instead of cropping it away.
  const [vbX, vbY, vbW] = viewBox.split(' ').map(Number);
  const captionX = vbX + vbW * 0.04;
  const captionY = vbY + vbW * 0.06;
  const captionSize = Math.max(26, Math.min(40, vbW * 0.034));
  // The clip is 1000×640; the halo and the crosshair are part of the original
  // composition and look wrong when they are scaled to a zoomed vector.
  const zoomed = kind === 'vectors' || kind === 'projection';
  if (kind === 'image_layers' && layers.length) {
    const phase = clamp(progress) * (layers.length - 1);
    const current = Math.min(layers.length - 1, Math.floor(phase));
    const next = Math.min(layers.length - 1, current + 1);
    const ranks = [1, 4, 12, 32];
    return <div style={{position: 'relative', width: '100%', height: '100%', display: 'flex', alignItems: 'center'}}>
      <div style={{position: 'relative', width: '100%', aspectRatio: '1.6', borderRadius: 24, overflow: 'hidden', border: `2px solid ${color}66`, boxShadow: `0 25px 100px ${color}16`}}>
        <Img src={staticFile(layers[current])} style={{position: 'absolute', width: '100%', height: '100%'}}/>
        <Img src={staticFile(layers[next])} style={{position: 'absolute', width: '100%', height: '100%', opacity: phase - current}}/>
        <div style={{position: 'absolute', bottom: 18, left: 22, color: '#fff4dd', fontSize: 25, background: '#07141cce', padding: '12px 18px', borderRadius: 12}}>
          真实 SVD · k = {ranks[current]}{next !== current ? ` → ${ranks[next]}` : ''}
        </div>
      </div>
    </div>;
  }
  let content: React.ReactNode;
  if (kind === 'matrix') {
    const transformProgress = ease(time / 4);
    const m = scene.matrix.map((v, i) => (i === 0 || i === 3 ? 1 : 0) * (1 - transformProgress) + v * transformProgress);
    const transform = (x: number, y: number) => [m[0] * x + m[1] * y, m[2] * x + m[3] * y];
    const point = (x: number, y: number) => {const [a, b] = transform(x, y); return `${px(a)},${py(b)}`;};
    const det = m[0] * m[3] - m[1] * m[2];
    content = <>
      {Array.from({length: 17}, (_, i) => (i - 8) / 2).map((k) => <g key={k} stroke={color} strokeOpacity={k === 0 ? 0.6 : 0.28} strokeWidth={k === 0 ? 2 : 1}>
        <polyline points={`${point(k, -4)} ${point(k, 4)}`} fill="none"/>
        <polyline points={`${point(-5, k)} ${point(5, k)}`} fill="none"/>
      </g>)}
      <polygon points={[point(0, 0), point(1, 0), point(1, 1), point(0, 1)].join(' ')} fill={color} fillOpacity="0.23" stroke={color} strokeWidth="3"/>
      <polygon points={[point(-1.8, -1.1), point(0.2, -1.1), point(0.2, 0.3), point(-0.8, 1.2), point(-1.8, 0.3)].join(' ')} fill="#ffc976" fillOpacity="0.09" stroke="#ffc976" strokeWidth="4"/>
      <polyline points={`${point(0, 0)} ${point(1, 0)}`} stroke="#ffc976" strokeWidth="5"/>
      <polyline points={`${point(0, 0)} ${point(0, 1)}`} stroke="#ff8e80" strokeWidth="5"/>
      {Array.from({length: 12}, (_, i) => {const [a, b] = transform(Math.sin(time * 0.3 + i) * 2.8, Math.cos(time * 0.25 + i * 1.7) * 2); return <circle key={i} cx={px(a)} cy={py(b)} r={3} fill="#fff2d7" opacity="0.7"/>;})}
      <g transform="translate(45, 28)" fill="#e9eedf" fontSize="40">
        <text x="0" y="47">A =</text>
        <path d="M95 3 H84 V80 H95 M282 3 H293 V80 H282" fill="none" stroke={color} strokeWidth="2.5"/>
        <text x="104" y="31">{m[0].toFixed(2)}</text><text x="205" y="31">{m[1].toFixed(2)}</text>
        <text x="104" y="69">{m[2].toFixed(2)}</text><text x="205" y="69">{m[3].toFixed(2)}</text>
      </g>
      <text x="48" y="610" style={{...textStyle, fill: color}}>det A = {det.toFixed(2)} · 面积倍数 = {Math.abs(det).toFixed(2)}</text>
    </>;
  } else if (kind === 'vectors') {
    // Pin the drawn vector to real coefficients when the DSL supplies them; the
    // narration usually quotes exact values, so a generic animated vector would
    // contradict it.
    const fixed = layer.series[0]?.values;
    const a = fixed && fixed.length >= 2 ? fixed[0] : 0.8 + p * 1.4;
    const b = fixed && fixed.length >= 2 ? fixed[1] : 1.3 - p * 0.7;
    content = <>
      {Array.from({length: 9}, (_, i) => i - 4).map(k => <g key={k} stroke="#ffffff" strokeOpacity="0.08"><line x1={px(k)} y1="0" x2={px(k)} y2="640"/><line x1="0" y1={py(k)} x2="1000" y2={py(k)}/></g>)}
      <line x1="500" y1="320" x2={px(a)} y2="320" stroke="#ffc976" strokeWidth="8"/>
      <line x1={px(a)} y1="320" x2={px(a)} y2={py(b)} stroke="#ff8e80" strokeWidth="8"/>
      <line x1="500" y1="320" x2={px(a)} y2={py(b)} stroke={color} strokeWidth="7" markerEnd="url(#arrow)"/>
      <circle cx={px(a)} cy={py(b)} r="13" fill={color}/>
      <text x={captionX} y={captionY} style={{...textStyle, fontSize: captionSize}}>v = {a.toFixed(2)} e₁ + {b.toFixed(2)} e₂</text>
      <text x={px(a / 2) - 30} y="360" style={{...textStyle, fill: '#ffc976'}}>{a.toFixed(1)} e₁</text>
      <text x={px(a) + 24} y={py(b / 2)} style={{...textStyle, fill: '#ff8e80'}}>{b.toFixed(1)} e₂</text>
    </>;
  } else if (kind === 'projection') {
    const fixed = layer.series[0]?.values;
    const direction = layer.series[1]?.values;
    const x = fixed && fixed.length >= 2 ? fixed[0] : 1.8 + Math.sin(time * 0.4) * 0.5;
    const y = fixed && fixed.length >= 2 ? fixed[1] : 2 - p * 0.5;
    const ux = direction && direction.length >= 2 ? direction[0] : 1;
    const uy = direction && direction.length >= 2 ? direction[1] : 0.5;
    const factor = (x * ux + y * uy) / (ux * ux + uy * uy);
    const qx = factor * ux, qy = factor * uy;
    content = <>
      <line x1={px(-4 * ux)} y1={py(-4 * uy)} x2={px(4 * ux)} y2={py(4 * uy)} stroke={color} strokeWidth="5"/>
      <line x1="500" y1="320" x2={px(x)} y2={py(y)} stroke="#ffc976" strokeWidth="5" markerEnd="url(#arrow)"/>
      <line x1={px(x)} y1={py(y)} x2={px(qx)} y2={py(qy)} stroke="#ff8e80" strokeWidth="4" strokeDasharray="9 8"/>
      <line x1="500" y1="320" x2={px(qx)} y2={py(qy)} stroke={color} strokeWidth="9"/>
      <circle cx={px(qx)} cy={py(qy)} r="11" fill={color}/>
      <circle cx={px(x)} cy={py(y)} r="11" fill="#ffc976"/>
      <text x={captionX} y={captionY} style={{...textStyle, fontSize: captionSize}}>projᵤ(v) = (v·u / u·u) u</text>
      <text x={px(x) + 20} y={py(y) - 18} style={{...textStyle, fill: '#ffc976'}}>原向量</text>
      <text x={px(qx) + 16} y={py(qy) + 44} style={{...textStyle, fill: color}}>投影</text>
    </>;
  } else if (kind === 'wave') {
    const line = (harmonics: number, offset: number, amp: number) => Array.from({length: 260}, (_, i) => {
      const t = i / 259 * Math.PI * 4 + time * 0.65;
      let y = 0;
      for (let k = 0; k < harmonics; k++) y += Math.sin(t * (2 * k + 1)) / (2 * k + 1);
      return `${40 + i / 259 * 920},${offset - y * amp}`;
    }).join(' ');
    content = <>
      {[0, 1, 2].map((i) => <g key={i}><line x1="40" y1={140 + i * 180} x2="960" y2={140 + i * 180} stroke="#ffffff" strokeOpacity="0.12"/><polyline fill="none" stroke={[color, '#ffc976', '#ff8e80'][i]} strokeWidth={i === 2 ? 4 : 2.5} points={line(i === 0 ? 1 : i === 1 ? 2 : 5, 140 + i * 180, 65)}/></g>)}
      
    </>;
  } else if (kind === 'network') {
    const nodes = Array.from({length: 14}, (_, i) => {const angle = i * 2.39996; const r = 60 + Math.sqrt(i / 13) * 220; return [500 + Math.cos(angle) * r * 1.3, 320 + Math.sin(angle) * r];});
    const edges = nodes.flatMap((a, i) => [1, 4].map(d => [a, nodes[(i + d) % nodes.length], i + d] as const));
    content = <>
      {edges.map(([a, b, seed], i) => {const f = (time * 0.18 + seed * 0.13) % 1; return <g key={i}>
        <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke={color} strokeOpacity="0.22" strokeWidth="2"/>
        <circle cx={a[0] + (b[0] - a[0]) * f} cy={a[1] + (b[1] - a[1]) * f} r="4" fill={color}/>
      </g>;})}
      {nodes.map(([x, y], i) => <g key={i}><circle cx={x} cy={y} r={17 + 3 * Math.sin(time * 1.5 + i)} fill="#142d3b" stroke={color} strokeWidth="2"/><text x={x} y={y + 6} textAnchor="middle" style={{...textStyle, fontSize: 17}}>{i + 1}</text></g>)}
      
    </>;
  } else {
    const a = time * 0.18, b = -0.45 + p * 0.7;
    const points = Array.from({length: 440}, (_, i) => {
      const t = i / 440 * Math.PI * 2;
      const x = (2 + Math.cos(3 * t)) * Math.cos(2 * t), y = (2 + Math.cos(3 * t)) * Math.sin(2 * t), z = Math.sin(3 * t);
      const x1 = x * Math.cos(a) + z * Math.sin(a), z1 = -x * Math.sin(a) + z * Math.cos(a);
      const y1 = y * Math.cos(b) - z1 * Math.sin(b), z2 = y * Math.sin(b) + z1 * Math.cos(b);
      const s = 105 * 7 / (7 + z2);
      return {x: 500 + x1 * s, y: 320 + y1 * s, z: z2};
    }).sort((a, b) => b.z - a.z);
    content = <>
      {[140, 240, 340].map(r => <ellipse key={r} cx="500" cy="320" rx={r * 1.2} ry={r * 0.55} fill="none" stroke={color} strokeOpacity="0.12"/>)}
      {points.map((v, i) => <circle key={i} cx={v.x} cy={v.y} r={3.6 - v.z * 0.4} fill={color} opacity={0.65 - v.z * 0.12}/>)}
      
    </>;
  }
  return <div style={{width: '100%', height: '100%', overflow: 'hidden', display: 'flex',
    alignItems: 'center', justifyContent: 'center'}}>
    {/* A zoomed drawing already matches the region's aspect ratio, so it fills the
        box; the fixed-aspect drawings keep their natural width to avoid cropping. */}
    <svg viewBox={viewBox} width={zoomed ? '100%' : svgWidth(box)} height="100%"
      style={{flexShrink: 0}}>
      <defs>
        <radialGradient id={`halo-${layer.id}`}><stop stopColor={color} stopOpacity="0.2"/><stop offset="1" stopColor={color} stopOpacity="0"/></radialGradient>
        <marker id="arrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10" fill={color}/></marker>
      </defs>
      {!zoomed && <>
        <ellipse cx="500" cy="320" rx="470" ry="310" fill={`url(#halo-${layer.id})`}/>
        <line x1="35" y1="320" x2="965" y2="320" stroke="#e7e3d0" strokeOpacity="0.22"/>
        <line x1="500" y1="20" x2="500" y2="620" stroke="#e7e3d0" strokeOpacity="0.22"/>
      </>}
      <g opacity={reveal}>{content}</g>
    </svg>
  </div>;
};


