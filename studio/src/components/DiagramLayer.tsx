import React from 'react';
import type {Layer} from '../types';
import type {Theme} from '../theme';
import {accent, accentDeep} from '../theme';
import type {Box} from '../Stage';

/**
 * Nodes and edges are drawn in the DSL's 1000×640 coordinate space, then the
 * viewBox is cropped to the content so a small diagram is not lost in a large
 * empty region.  Steps render below the cropped area.
 *
 * V2: edges curve slightly and carry a travelling packet, the node on the active
 * step is lifted with a halo, and steps read as a progress list instead of a
 * static numbered column.
 */
export const DiagramLayer: React.FC<{layer: Layer; theme: Theme; time: number; reveal: number; box: Box}> =
({layer, theme, time, reveal, box}) => {
  const color = accent[layer.color] || theme.text;
  const deep = accentDeep[layer.color] || color;
  const nodes = layer.nodes;
  const positions = new Map(nodes.map((node) => [node.id, node]));
  // Drop steps that just repeat the node labels: the same words twice at two sizes is
  // noise, and the tiny copy is unreadable on a phone.
  const steps = layer.steps.filter((step) => !nodes.some((node) => node.label.includes(step) || step.includes(node.label)));
  const active = steps.length ? Math.min(steps.length - 1, Math.floor(reveal * steps.length)) : -1;
  const widths = new Map(nodes.map((node) => [node.id, Math.max(210, node.label.length * 46 + 70)]));
  const pad = 48;
  const minX = Math.min(...nodes.map((node) => node.x - (widths.get(node.id) || 210) / 2)) - pad;
  const maxX = Math.max(...nodes.map((node) => node.x + (widths.get(node.id) || 210) / 2)) + pad;
  const minY = Math.min(...nodes.map((node) => node.y)) - 56 - pad;
  const maxY = Math.max(...nodes.map((node) => node.y)) + 56 + pad;
  const boxWidth = Math.max(1, maxX - minX);
  const boxHeight = Math.max(1, maxY - minY);
  const stepsHeight = steps.length ? steps.length * 52 + 26 : 0;
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
  const activeNode = active >= 0 && steps[active]
    ? nodes.find((node) => node.label.includes(steps[active]) || steps[active].includes(node.label))
    : undefined;
  return (
    <svg viewBox={viewBox} width="100%" height="100%" style={{overflow: 'hidden'}}>
      <defs>
        <marker id={`flow-${layer.id}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6"
          markerHeight="6" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10" fill={color} opacity="0.85"/>
        </marker>
        <linearGradient id={`node-${layer.id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={theme.surfaceAlt}/>
          <stop offset="100%" stopColor={theme.surface}/>
        </linearGradient>
        <filter id={`halo-${layer.id}`} x="-40%" y="-60%" width="180%" height="220%">
          <feGaussianBlur stdDeviation="14" result="blur"/>
          <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>
      {layer.edges.map((edge, index) => {
        const from = positions.get(edge.source);
        const to = positions.get(edge.target);
        if (!from || !to) return null;
        const appear = Math.min(1, Math.max(0, reveal * 1.6 - index * 0.12));
        const packet = (time * 0.32 + index * 0.27) % 1;
        // A shallow arc reads as a route; a straight line reads as a table border.
        const bend = 0.12 * Math.hypot(to.x - from.x, to.y - from.y);
        const midX = (from.x + to.x) / 2;
        const midY = (from.y + to.y) / 2 - bend;
        const labelY = Math.min(from.y, to.y) - 76;
        return <g key={`${edge.source}-${edge.target}-${index}`} opacity={appear}>
          <path d={`M${from.x} ${from.y} Q${midX} ${midY} ${to.x} ${to.y}`} fill="none"
            stroke={color} strokeOpacity={0.4} strokeWidth={3} markerEnd={`url(#flow-${layer.id})`}/>
          <circle cx={from.x + (to.x - from.x) * packet}
            cy={from.y + (to.y - from.y) * packet - bend * 2 * packet * (1 - packet)} r={6}
            fill={color} opacity={0.9}/>
          {edge.label && <>
            <rect x={midX - edge.label.length * 15 - 10} y={labelY - 26}
              width={edge.label.length * 30 + 20} height={36} rx={8}
              fill={theme.backgroundBase} fillOpacity={0.92}/>
            <text x={midX} y={labelY} textAnchor="middle" fill={theme.muted} fontSize={26}>{edge.label}</text>
          </>}
        </g>;
      })}
      {nodes.map((node, index) => {
        // A `draw` action on a diagram reveals the *connections*; blanking the boxes
        // until half the shot has passed left an empty frame under the first
        // sentence.  Nodes are always present, appearing from 35% opacity upward.
        const appear = Math.min(1, Math.max(0.35, reveal * 2 - index * 0.08));
        const width = widths.get(node.id) || 210;
        const isActive = activeNode?.id === node.id;
        return <g key={node.id} opacity={appear}>
          {isActive && <rect x={node.x - width / 2 - 10} y={node.y - 66} width={width + 20} height={132}
            rx={26} fill="none" stroke={deep} strokeWidth={3} opacity={0.55}
            filter={`url(#halo-${layer.id})`}/>}
          <rect x={node.x - width / 2} y={node.y - 56} width={width} height={112} rx={20}
            fill={`url(#node-${layer.id})`} stroke={isActive ? color : `${color}aa`} strokeWidth={isActive ? 5 : 4}/>
          <text x={node.x} y={node.y + 15} textAnchor="middle" fill={theme.text} fontSize={44}
            fontWeight={isActive ? 700 : 600}>
            {node.label}
          </text>
        </g>;
      })}
      {steps.map((step, index) => {
        const y = maxY + 24 + index * 52;
        const done = index < active;
        const current = index === active;
        return <g key={step} opacity={index <= active ? 1 : 0.34}>
          <rect x={minX + 8} y={y - 34} width={Math.min(boxWidth - 16, 62 + step.length * 30)} height={46}
            rx={10} fill={current ? `${color}26` : 'transparent'}
            stroke={current ? `${color}66` : 'transparent'} strokeWidth={2}/>
          <circle cx={minX + 34} cy={y - 11} r={11}
            fill={done ? color : 'transparent'} stroke={current ? color : theme.muted} strokeWidth={2.5}/>
          {done && <path d={`M${minX + 29} ${y - 11} l4 5 l7 -9`} fill="none" stroke={theme.backgroundBase}
            strokeWidth={3} strokeLinecap="round" strokeLinejoin="round"/>}
          <text x={minX + 58} y={y} fill={current ? theme.text : theme.muted} fontSize={30}
            fontWeight={current ? 700 : 500}>
            {step}
          </text>
        </g>;
      })}
    </svg>
  );
};
