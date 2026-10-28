import React from 'react';
import type {Sketch} from '../types';

/**
 * Hand-drawn annotation overlay.
 *
 * The geometry is a pure function of (box, kind, seed) — the same LCG and the same
 * formulas as `movelyth/sketch.py`, so Python can validate exactly what is drawn and
 * two renders of one frame are identical. Only the visible stroke grows with time, so
 * nothing wobbles while the viewer is reading.
 */
const MAX_OFFSET = 3;
const POINTS = 48;

const rng = (seed: number): (() => number) => {
  // Math.imul keeps the multiply inside 32 bits: a plain `state * 1103515245` loses
  // precision past 2^53 and drifts from the Python implementation used for checks.
  let state = (Math.imul(seed, 1103515245) + 12345) & 0x7fffffff;
  return () => {
    state = (Math.imul(state, 1103515245) + 12345) & 0x7fffffff;
    return state / 0x7fffffff;
  };
};

export const pathPoints = (box: {x: number; y: number; w: number; h: number},
  kind: string, seed: number): [number, number][] => {
  const {x, y, w, h} = box;
  const next = rng(seed);
  const points: [number, number][] = [];
  const round = (value: number) => Math.round(value * 100) / 100;
  if (kind === 'circle') {
    const cx = x + w / 2;
    const cy = y + h / 2;
    const rx = w * 0.52;
    const ry = h * 0.55;
    for (let index = 0; index < POINTS; index++) {
      const angle = -0.35 + (index / (POINTS - 1)) * 6.6;
      const wobble = 1 + (next() - 0.5) * 0.05;
      points.push([round(cx + rx * wobble * Math.cos(angle)), round(cy + ry * wobble * Math.sin(angle))]);
    }
  } else if (kind === 'underline') {
    for (let index = 0; index < POINTS; index++) {
      const t = index / (POINTS - 1);
      points.push([round(x + w * 0.04 + w * 0.92 * t), round(y + h * 0.96 + (next() - 0.5) * MAX_OFFSET)]);
    }
  } else if (kind === 'highlight') {
    for (let index = 0; index < POINTS; index++) {
      const t = index / (POINTS - 1);
      points.push([round(x + w * 0.02 + w * 0.96 * t),
        round(y + h * 0.55 + (next() - 0.5) * h * 0.35)]);
    }
  } else if (kind === 'bracket') {
    const half = POINTS / 2;
    for (let index = 0; index < half; index++) {
      const t = index / (half - 1);
      points.push([round(x - 18 + (next() - 0.5) * MAX_OFFSET), round(y + h * t)]);
    }
    for (let index = 0; index < half; index++) {
      const t = index / (half - 1);
      points.push([round(x - 18 + (next() - 0.5) * MAX_OFFSET), round(y + h - h * t)]);
    }
  } else {
    const corners: [number, number][] = [[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]];
    for (let index = 0; index < POINTS; index++) {
      const t = (index / (POINTS - 1)) * 4;
      const segment = Math.min(3, Math.floor(t));
      const local = t - segment;
      const [ax, ay] = corners[segment];
      const [bx, by] = corners[segment + 1];
      points.push([round(ax + (bx - ax) * local + (next() - 0.5) * MAX_OFFSET),
        round(ay + (by - ay) * local + (next() - 0.5) * MAX_OFFSET)]);
    }
  }
  return points;
};

const reveal = (progress: number, start: number, end: number): number => {
  if (end <= start) return progress >= end ? 1 : 0;
  return Math.max(0, Math.min(1, (progress - start) / (end - start)));
};

export const SketchOverlay: React.FC<{
  sketches: Sketch[];
  boxes: Record<string, {x: number; y: number; w: number; h: number}>;
  layerRegions: Record<string, string>;
  progress: number;
  color: string;
  width: number;
  height: number;
}> = ({sketches, boxes, layerRegions, progress, color, width, height}) => {
  if (!sketches.length) return null;
  return <svg width="100%" height="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none"
    style={{position: 'absolute', inset: 0, pointerEvents: 'none', overflow: 'visible'}}>
    {sketches.map((sketch) => {
      const box = boxes[layerRegions[sketch.target] || 'main'];
      if (!box) return null;
      const points = pathPoints(box, sketch.kind, sketch.seed);
      const path = 'M' + points.map(([px, py]) => `${px} ${py}`).join(' L');
      const visible = reveal(progress, Number(sketch.start), Number(sketch.end));
      if (visible <= 0) return null;
      const width = sketch.kind === 'highlight' ? 26 : 5;
      return <path key={sketch.id} d={path} fill="none" stroke={color} strokeWidth={width}
        strokeLinecap="round" strokeLinejoin="round" opacity={sketch.kind === 'highlight' ? 0.28 : 0.9}
        pathLength={1} strokeDasharray={1} strokeDashoffset={1 - visible}/>;
    })}
  </svg>;
};
