import React from 'react';
import type {Layer} from '../types';
import type {Theme} from '../theme';
import {accent} from '../theme';

/**
 * A horizontal milestone timeline: algorithm stages, protocol phases or a
 * historical sequence.  Steps come from the Scene DSL; the active step follows
 * the resolved action timing, so the highlight matches the narration.
 */
export const TimelineLayer: React.FC<{layer: Layer; theme: Theme; reveal: number; vertical: boolean}> =
({layer, theme, reveal, vertical}) => {
  const color = accent[layer.color] || theme.text;
  const steps = layer.steps.slice(0, 6);
  const count = steps.length;
  const left = vertical ? 120 : 90;
  const right = 1000 - (vertical ? 90 : 110);
  const y = vertical ? 330 : 330;
  const gap = count > 1 ? (right - left) / (count - 1) : 0;
  const active = Math.min(count - 1, Math.floor(reveal * count));
  return (
    <svg viewBox="0 0 1000 640" width="100%" height="100%" style={{overflow: 'hidden'}}>
      <line x1={left} y1={y} x2={right} y2={y} stroke={theme.grid} strokeOpacity={0.35} strokeWidth={5}/>
      <line x1={left} y1={y} x2={left + gap * active} y2={y} stroke={color} strokeWidth={7}
        opacity={active > 0 ? 1 : 0}/>
      {steps.map((step, index) => {
        const x = left + gap * index;
        const done = index <= active;
        const above = index % 2 === 0;
        const labelY = y + (above ? -92 : 96);
        const numberY = y + (above ? -46 : 54);
        return <g key={step} opacity={done ? 1 : 0.4}>
          <circle cx={x} cy={y} r={index === active ? 26 : 18}
            fill={index === active ? color : theme.surface} stroke={color} strokeWidth={4}/>
          <text x={x} y={numberY} textAnchor="middle" fontSize={index === active ? 40 : 34}
            fill={index === active ? theme.text : theme.muted} fontWeight={700}>
            {index + 1}
          </text>
          <text x={x} y={labelY} textAnchor="middle" fontSize={index === active ? 34 : 30}
            fill={index === active ? color : theme.muted} fontWeight={index === active ? 700 : 400}>
            {step}
          </text>
        </g>;
      })}
    </svg>
  );
};
