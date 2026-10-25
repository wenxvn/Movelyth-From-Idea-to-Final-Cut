import React from 'react';
import {Img, staticFile} from 'remotion';
import type {Scene} from './types';

export const palette = {cyan: '#68e5ed', amber: '#ffc976', coral: '#ff8e80', mint: '#9de2b6'};
const clamp = (v: number) => Math.max(0, Math.min(1, v));
const ease = (v: number) => { const p = clamp(v); return p * p * (3 - 2 * p); };
const px = (x: number) => 500 + x * 95;
const py = (y: number) => 320 - y * 95;

export const Visual: React.FC<{scene: Scene; time: number; progress: number; layers: string[]}> =
({scene, time, progress, layers}) => {
  const color = palette[scene.color];
  const p = ease(progress);
  const defs = <defs>
    <radialGradient id="halo"><stop stopColor={color} stopOpacity="0.2"/><stop offset="1" stopColor={color} stopOpacity="0"/></radialGradient>
    <linearGradient id="line"><stop stopColor={color}/><stop offset="1" stopColor="#f1e9d5"/></linearGradient>
    <marker id="arrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10" fill={color}/></marker>
  </defs>;
  const base = <>
    {defs}<ellipse cx="500" cy="320" rx="470" ry="310" fill="url(#halo)"/>
    <line x1="35" y1="320" x2="965" y2="320" stroke="#e7e3d0" strokeOpacity="0.22"/>
    <line x1="500" y1="20" x2="500" y2="620" stroke="#e7e3d0" strokeOpacity="0.22"/>
  </>;
  const textStyle = {fill: '#e9eedf', fontFamily: 'inherit', fontSize: 24};
  if (scene.visual === 'image_layers' && layers.length) {
    const phase = clamp(progress) * (layers.length - 1);
    const current = Math.min(layers.length - 1, Math.floor(phase));
    const next = Math.min(layers.length - 1, current + 1);
    const ranks = [1, 4, 12, 32];
    return <div style={{position: 'relative', width: '100%', height: '100%', display: 'flex', alignItems: 'center'}}>
      <div style={{position: 'relative', width: '100%', aspectRatio: '1.6', borderRadius: 28, overflow: 'hidden', border: `2px solid ${color}66`, boxShadow: `0 25px 100px ${color}16`}}>
        <Img src={staticFile(layers[current])} style={{position: 'absolute', width: '100%', height: '100%'}}/>
        <Img src={staticFile(layers[next])} style={{position: 'absolute', width: '100%', height: '100%', opacity: phase - current}}/>
        <div style={{position: 'absolute', bottom: 18, left: 22, color: '#fff4dd', fontSize: 25, background: '#07141cce', padding: '12px 18px', borderRadius: 12}}>真实 SVD · k = {ranks[current]}{next !== current ? ` → ${ranks[next]}` : ''}</div>
      </div>
    </div>;
  }
  let content: React.ReactNode;
  if (scene.visual === 'matrix') {
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
      <g transform="translate(45, 28)" fill="#e9eedf" fontSize="30">
        <text x="0" y="47">A =</text>
        <path d="M95 3 H84 V80 H95 M282 3 H293 V80 H282" fill="none" stroke={color} strokeWidth="2.5"/>
        <text x="104" y="31">{m[0].toFixed(2)}</text><text x="205" y="31">{m[1].toFixed(2)}</text>
        <text x="104" y="69">{m[2].toFixed(2)}</text><text x="205" y="69">{m[3].toFixed(2)}</text>
      </g>
      <text x="48" y="610" style={{...textStyle, fill: color}}>det A = {det.toFixed(2)} · 面积倍数 = {Math.abs(det).toFixed(2)}</text>
    </>;
  } else if (scene.visual === 'vectors') {
    const a = 0.8 + p * 1.4, b = 1.3 - p * 0.7;
    content = <>
      {Array.from({length: 9}, (_, i) => i - 4).map(k => <g key={k} stroke="#ffffff" strokeOpacity="0.08"><line x1={px(k)} y1="0" x2={px(k)} y2="640"/><line x1="0" y1={py(k)} x2="1000" y2={py(k)}/></g>)}
      <line x1="500" y1="320" x2={px(a)} y2="320" stroke="#ffc976" strokeWidth="7"/>
      <line x1={px(a)} y1="320" x2={px(a)} y2={py(b)} stroke="#ff8e80" strokeWidth="7"/>
      <line x1="500" y1="320" x2={px(a)} y2={py(b)} stroke={color} strokeWidth="6" markerEnd="url(#arrow)"/>
      <circle cx={px(a)} cy={py(b)} r="12" fill={color}/>
      <text x="50" y="70" style={textStyle}>v = {a.toFixed(2)} e₁ + {b.toFixed(2)} e₂</text>
      <text x={px(a / 2) - 30} y="355" style={{...textStyle, fill: '#ffc976'}}>a e₁</text>
      <text x={px(a) + 24} y={py(b / 2)} style={{...textStyle, fill: '#ff8e80'}}>b e₂</text>
    </>;
  } else if (scene.visual === 'projection') {
    const x = 1.8 + Math.sin(time * 0.4) * 0.5, y = 2 - p * 0.5;
    const factor = (x + y * 0.5) / 1.25;
    const qx = factor, qy = factor * 0.5;
    content = <>
      <line x1={px(-4)} y1={py(-2)} x2={px(4)} y2={py(2)} stroke={color} strokeWidth="4"/>
      <line x1="500" y1="320" x2={px(x)} y2={py(y)} stroke="#ffc976" strokeWidth="4" markerEnd="url(#arrow)"/>
      <line x1={px(x)} y1={py(y)} x2={px(qx)} y2={py(qy)} stroke="#ff8e80" strokeWidth="3" strokeDasharray="9 8"/>
      <line x1="500" y1="320" x2={px(qx)} y2={py(qy)} stroke={color} strokeWidth="8"/>
      <circle cx={px(qx)} cy={py(qy)} r="10" fill={color}/>
      <circle cx={px(x)} cy={py(y)} r="10" fill="#ffc976"/>
      <text x="45" y="80" style={textStyle}>projᵤ(v) = (v·u / u·u) u</text>
      <text x={px(x) + 20} y={py(y) - 15} style={{...textStyle, fill: '#ffc976'}}>原向量</text>
      <text x={px(qx) + 16} y={py(qy) + 38} style={{...textStyle, fill: color}}>投影</text>
    </>;
  } else if (scene.visual === 'wave') {
    const line = (harmonics: number, offset: number, amp: number) => Array.from({length: 260}, (_, i) => {
      const t = i / 259 * Math.PI * 4 + time * 0.65;
      let y = 0;
      for (let k = 0; k < harmonics; k++) y += Math.sin(t * (2 * k + 1)) / (2 * k + 1);
      return `${40 + i / 259 * 920},${offset - y * amp}`;
    }).join(' ');
    content = <>
      {[0, 1, 2].map((i) => <g key={i}><line x1="40" y1={140 + i * 180} x2="960" y2={140 + i * 180} stroke="#ffffff" strokeOpacity="0.12"/><polyline fill="none" stroke={[color, '#ffc976', '#ff8e80'][i]} strokeWidth={i === 2 ? 4 : 2.5} points={line(i === 0 ? 1 : i === 1 ? 2 : 5, 140 + i * 180, 65)}/></g>)}
      <text x="45" y="42" style={textStyle}>简单谐波 → 叠加 → 复杂形状</text>
    </>;
  } else if (scene.visual === 'network') {
    const nodes = Array.from({length: 14}, (_, i) => {const angle = i * 2.39996; const r = 60 + Math.sqrt(i / 13) * 220; return [500 + Math.cos(angle) * r * 1.3, 320 + Math.sin(angle) * r];});
    const edges = nodes.flatMap((a, i) => [1, 4].map(d => [a, nodes[(i + d) % nodes.length], i + d] as const));
    content = <>
      {edges.map(([a, b, seed], i) => {const f = (time * 0.18 + seed * 0.13) % 1; return <g key={i}>
        <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke={color} strokeOpacity="0.22" strokeWidth="2"/>
        <circle cx={a[0] + (b[0] - a[0]) * f} cy={a[1] + (b[1] - a[1]) * f} r="4" fill={color}/>
      </g>;})}
      {nodes.map(([x, y], i) => <g key={i}><circle cx={x} cy={y} r={17 + 3 * Math.sin(time * 1.5 + i)} fill="#142d3b" stroke={color} strokeWidth="2"/><text x={x} y={y + 6} textAnchor="middle" style={{...textStyle, fontSize: 17}}>{i + 1}</text></g>)}
      <text x="45" y="52" style={textStyle}>节点与连接 · 原理示意</text>
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
      <text x="45" y="54" style={textStyle}>三维点云 · 旋转保持距离</text>
    </>;
  }
  return <svg viewBox="0 0 1000 640" width="100%" height="100%" style={{overflow: 'hidden'}}>{base}{content}</svg>;
};
