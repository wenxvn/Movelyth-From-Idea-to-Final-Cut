import React from 'react';
import type {Layer} from '../types';
import type {Theme} from '../theme';
import {accent} from '../theme';

export const ShapeLayer: React.FC<{layer: Layer; theme: Theme; reveal: number}> =
({layer, theme, reveal}) => {
  const color = accent[layer.color] || theme.text;
  const points = layer.points.length >= 2 ? layer.points : [500, 320];
  const pair = (index: number): [number, number] => [points[index * 2] ?? 500, points[index * 2 + 1] ?? 320];
  const [x1, y1] = pair(0);
  const [x2, y2] = pair(1);
  const dash = 1 - reveal;
  const common = {stroke: color, strokeWidth: 4, fill: 'none', pathLength: 1, strokeDasharray: 1, strokeDashoffset: dash};
  let shape: React.ReactNode;
  switch (layer.shape) {
    case 'point':
      shape = <circle cx={x1} cy={y1} r={10 + 4 * reveal} fill={color} opacity={reveal} />;
      break;
    case 'line':
      shape = <line x1={x1} y1={y1} x2={x2} y2={y2} {...common} />;
      break;
    case 'circle':
      shape = <circle cx={x1} cy={y1} r={Math.max(20, points[2] ?? 120)} {...common} />;
      break;
    case 'arrow':
      shape = <>
        <defs>
          <marker id={`arrow-${layer.id}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10" fill={color}/>
          </marker>
        </defs>
        <line x1={x1} y1={y1} x2={x2} y2={y2} {...common} markerEnd={`url(#arrow-${layer.id})`} />
      </>;
      break;
    case 'polygon':
      shape = <polygon points={points.reduce<string[]>((all, value, i) =>
        i % 2 === 0 ? [...all, `${value},${points[i + 1] ?? 0}`] : all, []).join(' ')}
        {...common} fill={`${color}22`} />;
      break;
    case 'bracket':
      shape = <path d={`M ${x1 + 40} ${y1} H ${x1} V ${y2} H ${x1 + 40}`} {...common} strokeWidth={5} />;
      break;
    case 'rect':
    default:
      shape = <rect x={x1} y={y1} width={Math.max(20, (points[2] ?? 300) - x1)} height={Math.max(20, (points[3] ?? 200) - y1)}
        rx={theme.radius} {...common} fill={`${color}18`} />;
      break;
  }
  return <svg viewBox="0 0 1000 640" width="100%" height="100%" style={{overflow: 'visible'}}>{shape}</svg>;
};
