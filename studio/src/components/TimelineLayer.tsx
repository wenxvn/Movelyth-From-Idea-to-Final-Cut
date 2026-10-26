import React from 'react';
import type {Layer} from '../types';
import type {Theme} from '../theme';
import {accent} from '../theme';

/**
 * Horizontal milestone strip.  The viewBox is cropped to the strip so a short
 * three-step timeline fills the frame instead of floating in a large canvas.
 */
export const TimelineLayer: React.FC<{layer: Layer; theme: Theme; reveal: number; vertical: boolean}> =
({layer, theme, reveal, vertical}) => {
  const color = accent[layer.color] || theme.text;
  const steps = layer.steps.slice(0, 6);
  const count = steps.length;
  const left = 150;
  const right = 1000 - 150;
  const gap = count > 1 ? (right - left) / (count - 1) : 0;
  const y = 320;
  const active = Math.min(count - 1, Math.floor(reveal * count));
  const minX = 40;
  const minY = 120;
  const maxY = 520;
  return (
    <svg viewBox={`${minX} ${minY} ${1000 - minX * 2} ${maxY - minY}`} width="100%" height="100%"
      style={{overflow: 'hidden'}}>
      <line x1={left} y1={y} x2={right} y2={y} stroke={theme.grid} strokeOpacity={0.35} strokeWidth={6}/>
      <line x1={left} y1={y} x2={left + gap * active} y2={y} stroke={color} strokeWidth={9}
        opacity={active > 0 ? 1 : 0}/>
      {steps.map((step, index) => {
        const x = left + gap * index;
        const done = index <= active;
        const above = index % 2 === 0;
        const labelY = y + (above ? -110 : 120);
        const numberY = y + (above ? -50 : 62);
        return <g key={step} opacity={done ? 1 : 0.4}>
          <circle cx={x} cy={y} r={index === active ? 30 : 20}
            fill={index === active ? color : theme.surface} stroke={color} strokeWidth={5}/>
          <text x={x} y={numberY} textAnchor="middle" fontSize={index === active ? 46 : 38}
            fill={index === active ? theme.text : theme.muted} fontWeight={700}>
            {index + 1}
          </text>
          <text x={x} y={labelY} textAnchor="middle" fontSize={index === active ? 40 : 34}
            fill={index === active ? color : theme.muted} fontWeight={index === active ? 700 : 400}>
            {step}
          </text>
        </g>;
      })}
    </svg>
  );
};
