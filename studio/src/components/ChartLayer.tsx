import React from 'react';
import type {Layer} from '../types';
import type {Theme} from '../theme';
import {accent} from '../theme';
import type {Box} from '../Stage';

const palette = (layer: Layer): string[] => {
  const first = accent[layer.color] || '#68e5ed';
  const others = ['#ffc976', '#ff8e80', '#9de2b6'].filter((color) => color !== first);
  return [first, ...others];
};

const ticks = (min: number, max: number, count = 4): number[] => {
  const step = (max - min) / count;
  return Array.from({length: count + 1}, (_, i) => min + step * i);
};

const format = (value: number): string => {
  if (Math.abs(value) >= 1000) return value.toFixed(0);
  if (Math.abs(value) >= 10) return value.toFixed(1).replace(/\.0$/, '');
  return value.toFixed(2).replace(/0$/, '').replace(/\.$/, '');
};

export const ChartLayer: React.FC<{layer: Layer; theme: Theme; reveal: number; vertical: boolean; box?: Box}> =
({layer, theme, reveal, vertical, box}) => {
  const series = layer.series.filter((s) => s.values.length >= 2);
  if (!series.length) {
    return <div style={{color: theme.muted, fontSize: 26}}>缺少数据，不能凭空绘制曲线</div>;
  }
  // Draw on a canvas whose aspect ratio matches the region, so a wide short box is not
  // letterboxed into a small chart with large empty margins.
  const regionAspect = box ? Math.max(0.8, Math.min(3.2, box.w / Math.max(1, box.h))) : 1000 / 640;
  const canvasWidth = Math.round(640 * regionAspect);
  // Keep text visually the same size when the canvas gets wider than the base 1000.
  const font = (size: number): number => Math.round(size * Math.max(1, canvasWidth / 1000));
  // Explicit x coordinates (polygon vertices, uneven sampling) take precedence over index.
  const explicitX = series.every((s) => s.x_values && s.x_values.length === s.values.length);
  const xs = series.flatMap((s) => (explicitX ? s.x_values : s.values.map((_v, i) => i)));
  const ys = series.flatMap((s) => s.values);
  const rawXMin = Math.min(...xs);
  const rawXMax = Math.max(...xs);
  const xSpan = rawXMax - rawXMin || 1;
  const xMin = rawXMin - xSpan * 0.08;
  const xMax = rawXMax + xSpan * 0.08;
  const rawMin = Math.min(...ys);
  const rawMax = Math.max(...ys);
  const span = rawMax - rawMin || Math.max(1, Math.abs(rawMax) * 0.2);
  const min = rawMin - span * 0.12;
  const max = rawMax + span * 0.12;
  const left = vertical ? 96 : 88;
  const right = 44;
  const top = 48;
  const bottom = 96;
  const width = canvasWidth - left - right;
  const height = 640 - top - bottom;
  const xAt = (value: number): number => left + ((value - xMin) / (xMax - xMin)) * width;
  const yAt = (value: number): number => top + height - ((value - min) / (max - min)) * height;
  const colors = palette(layer);
  const grid = ticks(min, max).map((value) => ({value, y: yAt(value)}));
  const xTicks = ticks(xMin, xMax, 4).map((value) => ({value, x: xAt(value)}));
  const count = Math.max(...series.map((s) => s.values.length));
  const barWidth = Math.max(6, (width / count) * 0.55);
  // Bars grow from zero (or the axis floor when all values are negative), so a 0 value
  // renders as no bar at all instead of a floating stub.
  const baseline = yAt(Math.max(0, min));
  return (
    <svg viewBox={`0 0 ${canvasWidth} 640`} width="100%" height="100%" style={{overflow: 'hidden'}}>
      {grid.map((tick, index) => <g key={`y${tick.value}`}>
        <line x1={left} y1={tick.y} x2={left + width} y2={tick.y} stroke={theme.grid} strokeOpacity={0.18}/>
        {index > 0 && index < grid.length - 1 && <text x={left - 14} y={tick.y + 7} textAnchor="end"
          fill={theme.muted} fontSize={font(26)}>{format(tick.value)}</text>}
      </g>)}
      {xTicks.map((tick) => tick.x > left + 60 && tick.x < left + width - 40
        ? <text key={`x${tick.value}`} x={tick.x} y={top + height + 34} textAnchor="middle"
          fill={theme.muted} fontSize={font(25)}>{format(tick.value)}</text>
        : null)}
      <line x1={left} y1={top + height} x2={left + width} y2={top + height} stroke={theme.grid} strokeOpacity={0.5}/>
      <line x1={left} y1={top} x2={left} y2={top + height} stroke={theme.grid} strokeOpacity={0.5}/>
      {series.map((s, sIndex) => {
        const color = colors[sIndex % colors.length];
        const xValues = explicitX ? s.x_values : s.values.map((_v, i) => i);
        const points = s.values.map((value, index) => [xAt(xValues[index]), yAt(value)] as const);
        if (layer.chart === 'bar') {
          return <g key={s.label}>{s.values.map((value, index) => {
            const x = xAt(xValues[index]) - barWidth / 2;
            const y = yAt(value);
            const full = Math.abs(baseline - y);
            const h = full * reveal;
            const topY = value >= 0 ? baseline - h : baseline;
            return <g key={index}>
              <rect x={x} y={topY} width={barWidth} height={h} fill={color} opacity={0.82} rx={3}/>
              {value === 0 && <text x={x + barWidth / 2} y={baseline - 10} textAnchor="middle"
                fill={theme.muted} fontSize={font(24)}>0</text>}
            </g>;
          })}</g>;
        }
        if (layer.chart === 'scatter') {
          const path = points.map(([x, y], index) => `${index === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
          return <g key={s.label}>
            {layer.connect && <path d={`${path} Z`} fill={`${color}1f`} stroke={color} strokeWidth={5}
              strokeLinejoin="round" opacity={0.95}/>}
            {points.map(([x, y], index) =>
              <circle key={index} cx={x} cy={y} r={10} fill={color}
                opacity={reveal > index / Math.max(1, points.length) ? 0.95 : 0.2}/>)}
          </g>;
        }
        const d = points.map(([x, y], index) => `${index === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
        const last = points[points.length - 1];
        const label = (x: number, y: number, text: string, anchor: 'start' | 'end') => {
          const labelWidth = text.length * 12 + 16;
          const leftEdge = anchor === 'start' ? x + 10 : x - labelWidth - 10;
          const labelTop = Math.min(top + height - 26, Math.max(top + 4, y - 36));
          return <g>
            <rect x={leftEdge} y={labelTop} width={labelWidth} height={26} rx={5} fill={theme.surface} fillOpacity={0.92}/>
            <text x={leftEdge + 8} y={labelTop + 19} fill={color} fontSize={font(24)}>{text}</text>
          </g>;
        };
        return <g key={s.label}>
          <path d={d} fill="none" stroke={color} strokeWidth={6} strokeLinecap="round" pathLength={1}
            strokeDasharray={1} strokeDashoffset={1 - reveal}/>
          {points.map(([x, y], index) => <circle key={index} cx={x} cy={y} r={5} fill={color} opacity={reveal}/>)}
          {label(points[0][0], points[0][1], format(s.values[0]), 'start')}
          {label(last[0], last[1], format(s.values[s.values.length - 1]), 'end')}
        </g>;
      })}
      <text x={left} y={640 - 6} fill={theme.muted} fontSize={font(22)}>
        {[layer.axis || (explicitX ? 'x' : '步骤'), layer.unit || series[0].unit].filter(Boolean).join(' · ')}
      </text>
      {layer.source_note && <text x={left + width} y={top - 16} textAnchor="end" fill={theme.muted} fontSize={font(20)}>
        {layer.source_note}
      </text>}
      {series.length > 1 && <g transform={`translate(${left + 14}, ${top + 8})`}>
        {series.map((s, index) => <g key={s.label} transform={`translate(0, ${index * 30})`}>
          <rect width={16} height={16} y={3} fill={colors[index % colors.length]} rx={3}/>
          <text x={26} y={18} fill={theme.text} fontSize={font(24)}>{s.label}</text>
        </g>)}
      </g>}
    </svg>
  );
};




