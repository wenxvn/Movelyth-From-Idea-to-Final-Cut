import React from 'react';
import type {Layer} from '../types';
import type {Theme} from '../theme';
import {accent} from '../theme';

export const DiagramLayer: React.FC<{layer: Layer; theme: Theme; time: number; reveal: number}> =
({layer, theme, time, reveal}) => {
  const color = accent[layer.color] || theme.text;
  const nodes = layer.nodes;
  const positions = new Map(nodes.map((node) => [node.id, node]));
  const steps = layer.steps;
  const active = steps.length ? Math.min(steps.length - 1, Math.floor(reveal * steps.length)) : -1;
  return (
    <svg viewBox="0 0 1000 640" width="100%" height="100%" style={{overflow: 'hidden'}}>
      <defs>
        <marker id={`flow-${layer.id}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10" fill={color} opacity="0.85"/>
        </marker>
      </defs>
      {layer.edges.map((edge, index) => {
        const from = positions.get(edge.source);
        const to = positions.get(edge.target);
        if (!from || !to) return null;
        const appear = Math.min(1, Math.max(0, reveal * 1.6 - index * 0.12));
        const packet = (time * 0.35 + index * 0.27) % 1;
        return <g key={`${edge.source}-${edge.target}-${index}`} opacity={appear}>
          <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke={color} strokeOpacity={0.45} strokeWidth={3}
            markerEnd={`url(#flow-${layer.id})`}/>
          <circle cx={from.x + (to.x - from.x) * packet} cy={from.y + (to.y - from.y) * packet} r={6} fill={color}/>
          {edge.label && <text x={(from.x + to.x) / 2} y={(from.y + to.y) / 2 - 10} textAnchor="middle"
            fill={theme.muted} fontSize={17}>{edge.label}</text>}
        </g>;
      })}
      {nodes.map((node, index) => {
        const appear = Math.min(1, Math.max(0, reveal * 2 - index * 0.08));
        const width = Math.max(150, node.label.length * 32 + 48);
        return <g key={node.id} opacity={appear}>
          <rect x={node.x - width / 2} y={node.y - 42} width={width} height={84} rx={16}
            fill={theme.surface} stroke={color} strokeWidth={4}/>
          <text x={node.x} y={node.y + 10} textAnchor="middle" fill={theme.text} fontSize={30}>
            {node.label}
          </text>
        </g>;
      })}
      {steps.map((step, index) => <g key={step} opacity={index <= active ? 1 : 0.32}>
        <rect x={40} y={470 + index * 30} width={Math.min(920, 34 + step.length * 18)} height={28} rx={6}
          fill={index === active ? `${color}33` : 'transparent'}/>
        <text x={50} y={493 + index * 30} fill={index === active ? theme.text : theme.muted} fontSize={23}>
          {index + 1}. {step}
        </text>
      </g>)}
    </svg>
  );
};

