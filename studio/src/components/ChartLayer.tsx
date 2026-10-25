import React from 'react';
import type {Layer} from '../types';
import type {Theme} from '../theme';
import {accent} from '../theme';

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

export const ChartLayer: React.FC<{layer: Layer; theme: Theme; reveal: number; vertical: boolean}> =
({layer, theme, reveal, vertical}) => {
  const series = layer.series.filter((s) => s.values.length >= 2);
  if (!series.length) {
    return <div style={{color: theme.muted, fontSize: 26}}>缺少数据，不能凭空绘制曲线</div>;
  }
  const all = series.flatMap((s) => s.values);
  const rawMin = Math.min(...all);
  const rawMax = Math.max(...all);
  const span = rawMax - rawMin || Math.max(1, Math.abs(rawMax) * 0.2);
  const min = rawMin - span * 0.12;
  const max = rawMax + span * 0.12;
  const left = vertical ? 92 : 84;
  const right = 36;
  const top = 42;
  const bottom = 74;
  const width = 1000 - left - right;
  const height = 640 - top - bottom;
  const xAt = (index: number, count: number): number => left + (count <= 1 ? width / 2 : (index / (count - 1)) * width);
  const yAt = (value: number): number => top + height - ((value - min) / (max - min)) * height;
  const colors = palette(layer);
  const grid = ticks(min, max).map((value) => ({value, y: yAt(value)}));
  const count = Math.max(...series.map((s) => s.values.length));
  const barWidth = Math.max(6, (width / count) * 0.55);
  return (
    <svg viewBox="0 0 1000 640" width="100%" height="100%" style={{overflow: 'hidden'}}>
      {grid.map((tick) => <g key={tick.value}>
        <line x1={left} y1={tick.y} x2={left + width} y2={tick.y} stroke={theme.grid} strokeOpacity={0.18}/>
        <text x={left - 12} y={tick.y + 6} textAnchor="end" fill={theme.muted} fontSize={22}>{format(tick.value)}</text>
      </g>)}
      <line x1={left} y1={top + height} x2={left + width} y2={top + height} stroke={theme.grid} strokeOpacity={0.5}/>
      <line x1={left} y1={top} x2={left} y2={top + height} stroke={theme.grid} strokeOpacity={0.5}/>
      {series.map((s, sIndex) => {
        const color = colors[sIndex % colors.length];
        const points = s.values.map((value, index) => [xAt(index, s.values.length), yAt(value)] as const);
        if (layer.chart === 'bar') {
          return <g key={s.label}>{s.values.map((value, index) => {
            const x = xAt(index, s.values.length) - barWidth / 2;
            const y = yAt(value);
            const h = (top + height - y) * reveal;
            return <rect key={index} x={x} y={top + height - h} width={barWidth} height={h} fill={color} opacity={0.82} rx={3}/>;
          })}</g>;
        }
        if (layer.chart === 'scatter') {
          const path = points.map(([x, y], index) => `${index === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
          return <g key={s.label}>
            {layer.connect && <path d={`${path} Z`} fill={`${color}18`} stroke={color} strokeWidth={4}
              strokeLinejoin="round" opacity={0.9}/>}
            {points.map(([x, y], index) =>
              <circle key={index} cx={x} cy={y} r={9} fill={color}
                opacity={reveal > index / Math.max(1, points.length) ? 0.95 : 0.2}/>)}
          </g>;
        }
        const d = points.map(([x, y], index) => `${index === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
        const last = points[points.length - 1];
        const label = (x: number, y: number, text: string, anchor: 'start' | 'end') => {
          const width = text.length * 11 + 14;
          const left = anchor === 'start' ? x + 8 : x - width - 8;
          const labelTop = Math.min(top + height - 24, Math.max(top + 4, y - 34));
          return <g>
            <rect x={left} y={labelTop} width={width} height={24} rx={5} fill={theme.surface} fillOpacity={0.92}/>
            <text x={left + 7} y={labelTop + 17} fill={color} fontSize={20}>{text}</text>
          </g>;
        };
        return <g key={s.label}>
          <path d={d} fill="none" stroke={color} strokeWidth={5} strokeLinecap="round" pathLength={1}
            strokeDasharray={1} strokeDashoffset={1 - reveal}/>
          {points.map(([x, y], index) => <circle key={index} cx={x} cy={y} r={4.5} fill={color} opacity={reveal}/>)}
          {label(points[0][0], points[0][1], format(s.values[0]), 'start')}
          {label(last[0], last[1], format(s.values[s.values.length - 1]), 'end')}
        </g>;
      })}
      <text x={left} y={640 - 24} fill={theme.muted} fontSize={22}>{layer.axis || '步骤'}</text>
      <text x={left + width} y={640 - 24} textAnchor="end" fill={theme.muted} fontSize={22}>{layer.unit || series[0].unit}</text>
      {layer.source_note && <text x={left + width} y={top - 14} textAnchor="end" fill={theme.muted} fontSize={17}>
        {layer.source_note}
      </text>}
      {series.length > 1 && <g transform={`translate(${left + 12}, ${top + 6})`}>
        {series.map((s, index) => <g key={s.label} transform={`translate(0, ${index * 26})`}>
          <rect width={14} height={14} y={2} fill={colors[index % colors.length]} rx={3}/>
          <text x={22} y={15} fill={theme.text} fontSize={20}>{s.label}</text>
        </g>)}
      </g>}
    </svg>
  );
};




