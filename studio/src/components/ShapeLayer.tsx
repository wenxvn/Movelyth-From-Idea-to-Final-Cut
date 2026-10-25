import React from 'react';
import type {Layer} from '../types';
import type {Theme} from '../theme';
import {accent} from '../theme';

const pairs = (points: number[]): [number, number][] => {
  const result: [number, number][] = [];
  for (let index = 0; index + 1 < points.length; index += 2) {
    result.push([points[index], points[index + 1]]);
  }
  return result.length ? result : [[500, 320]];
};

export const ShapeLayer: React.FC<{layer: Layer; theme: Theme; reveal: number}> =
({layer, theme, reveal}) => {
  const color = accent[layer.color] || theme.text;
  const vertices = pairs(layer.points);
  const [x1, y1] = vertices[0];
  const [x2, y2] = vertices[1] || vertices[0];
  const common = {stroke: color, strokeWidth: 5, fill: 'none', pathLength: 1, strokeDasharray: 1,
    strokeDashoffset: 1 - reveal};
  let shape: React.ReactNode;
  switch (layer.shape) {
    case 'point':
      shape = <circle cx={x1} cy={y1} r={12 + 4 * reveal} fill={color} opacity={reveal} />;
      break;
    case 'line':
      // Every supplied pair is a vertex: draw the whole polyline, not just the first segment.
      // With connect=true the polyline reads as a directed route: start dot plus arrow head.
      shape = <>
        {layer.connect && <defs>
          <marker id={`path-${layer.id}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6"
            markerHeight="6" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10" fill={color}/>
          </marker>
        </defs>}
        <polyline points={vertices.map(([x, y]) => `${x},${y}`).join(' ')} {...common}
          strokeLinejoin="round" strokeLinecap="round" strokeWidth={7}
          markerEnd={layer.connect ? `url(#path-${layer.id})` : undefined}/>
        {layer.connect && <circle cx={x1} cy={y1} r={11} fill={color}/>}
      </>;
      break;
    case 'circle':
      shape = <circle cx={x1} cy={y1} r={Math.max(24, vertices[1]?.[0] ?? 120)} {...common} />;
      break;
    case 'arrow':
      shape = <>
        <defs>
          <marker id={`arrow-${layer.id}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6"
            markerHeight="6" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10" fill={color}/>
          </marker>
        </defs>
        <line x1={x1} y1={y1} x2={x2} y2={y2} {...common} strokeWidth={7}
          markerEnd={`url(#arrow-${layer.id})`} />
      </>;
      break;
    case 'polygon':
      shape = <polygon points={vertices.map(([x, y]) => `${x},${y}`).join(' ')}
        {...common} fill={`${color}22`} strokeWidth={6}/>;
      break;
    case 'bracket':
      shape = <path d={`M ${x1 + 50} ${y1} H ${x1} V ${y2} H ${x1 + 50}`} {...common} strokeWidth={6} />;
      break;
    case 'rect':
    default:
      shape = <rect x={x1} y={y1} width={Math.max(20, x2 - x1)} height={Math.max(20, y2 - y1)}
        rx={theme.radius} {...common} fill={`${color}18`} />;
      break;
  }
  return <svg viewBox="0 0 1000 640" width="100%" height="100%" style={{overflow: 'visible'}}>{shape}</svg>;
};
