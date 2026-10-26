import React from 'react';
import type {Layer} from '../types';
import type {Theme} from '../theme';
import {accent} from '../theme';
import type {Box} from '../Stage';

/**
 * Nodes and edges are drawn in the DSL's 1000×640 coordinate space, then the
 * viewBox is cropped to the content so a small diagram is not lost in a large
 * empty region.  Steps render below the cropped area.
 */
export const DiagramLayer: React.FC<{layer: Layer; theme: Theme; time: number; reveal: number; box: Box}> =
({layer, theme, time, reveal, box}) => {
  const color = accent[layer.color] || theme.text;
  const nodes = layer.nodes;
  const positions = new Map(nodes.map((node) => [node.id, node]));
  const steps = layer.steps;
  const active = steps.length ? Math.min(steps.length - 1, Math.floor(reveal * steps.length)) : -1;
  const widths = new Map(nodes.map((node) => [node.id, Math.max(210, node.label.length * 46 + 70)]));
  const pad = 48;
  const minX = Math.min(...nodes.map((node) => node.x - (widths.get(node.id) || 210) / 2)) - pad;
  const maxX = Math.max(...nodes.map((node) => node.x + (widths.get(node.id) || 210) / 2)) + pad;
  const minY = Math.min(...nodes.map((node) => node.y)) - 56 - pad;
  const maxY = Math.max(...nodes.map((node) => node.y)) + 56 + pad;
  const boxWidth = Math.max(1, maxX - minX);
  const boxHeight = Math.max(1, maxY - minY);
  const stepsHeight = steps.length ? steps.length * 46 + 24 : 0;
  // Match the region's aspect ratio so a wide, short flow still fills a tall region
  // instead of shrinking into a thin band with large empty space.
  const regionAspect = Math.max(0.6, box.w / Math.max(1, box.h));
  const contentHeight = boxHeight + stepsHeight;
  const contentAspect = boxWidth / Math.max(1, contentHeight);
  let viewW = boxWidth;
  let viewH = contentHeight;
  if (contentAspect > regionAspect) {
    viewH = boxWidth / regionAspect;
  } else {
    viewW = contentHeight * regionAspect;
  }
  const viewX = minX - (viewW - boxWidth) / 2;
  const viewY = minY - (viewH - contentHeight) / 2;
  const viewBox = `${viewX} ${viewY} ${viewW} ${viewH}`;
  return (
    <svg viewBox={viewBox} width="100%" height="100%" style={{overflow: 'hidden'}}>
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
        const midX = (from.x + to.x) / 2;
        // Edge labels sit above the nodes so a short gap between boxes cannot cover them.
        const labelY = Math.min(from.y, to.y) - 76;
        return <g key={`${edge.source}-${edge.target}-${index}`} opacity={appear}>
          <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke={color} strokeOpacity={0.45} strokeWidth={3}
            markerEnd={`url(#flow-${layer.id})`}/>
          <circle cx={from.x + (to.x - from.x) * packet} cy={from.y + (to.y - from.y) * packet} r={6} fill={color}/>
          {edge.label && <>
            <rect x={midX - edge.label.length * 15 - 10} y={labelY - 26} width={edge.label.length * 30 + 20}
              height={36} rx={6} fill={theme.background} fillOpacity={0.9}/>
            <text x={midX} y={labelY} textAnchor="middle" fill={theme.muted} fontSize={26}>{edge.label}</text>
          </>}
        </g>;
      })}
      {nodes.map((node, index) => {
        const appear = Math.min(1, Math.max(0, reveal * 2 - index * 0.08));
        const width = widths.get(node.id) || 210;
        return <g key={node.id} opacity={appear}>
          <rect x={node.x - width / 2} y={node.y - 56} width={width} height={112} rx={20}
            fill={theme.surface} stroke={color} strokeWidth={4}/>
          <text x={node.x} y={node.y + 15} textAnchor="middle" fill={theme.text} fontSize={44}>
            {node.label}
          </text>
        </g>;
      })}
      {steps.map((step, index) => {
        const y = maxY + 24 + index * 46;
        return <g key={step} opacity={index <= active ? 1 : 0.32}>
          <rect x={minX + 8} y={y - 30} width={Math.min(boxWidth - 16, 40 + step.length * 30)} height={40} rx={8}
            fill={index === active ? `${color}33` : 'transparent'}/>
          <text x={minX + 18} y={y} fill={index === active ? theme.text : theme.muted} fontSize={30}>
            {index + 1}. {step}
          </text>
        </g>;
      })}
    </svg>
  );
};
