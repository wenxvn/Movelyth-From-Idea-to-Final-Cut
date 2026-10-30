import React from 'react';
import type {Annotation, Layer, Scene, Series} from '../types';
import type {Theme} from '../theme';
import {accent, accentDeep} from '../theme';
import type {Box} from '../Stage';
import {measureText} from '../layouts';
import {annotationsFor, type Beat, formatValue} from '../insights';

const palette = (layer: Layer): string[] => {
  const first = accent[layer.color] || '#6fe6ef';
  const others = ['#ffc978', '#ff9285', '#a3e8bd'].filter((color) => color !== first);
  return [first, ...others];
};

/** 1-2-5 rounding, so ticks read as 0 / 2 / 4 / 6 instead of 0.76 / 2.0 / 3.24. */
const niceStep = (range: number, target = 4): number => {
  if (!Number.isFinite(range) || range <= 0) return 1;
  const raw = range / target;
  const magnitude = Math.pow(10, Math.floor(Math.log10(raw)));
  const normal = raw / magnitude;
  const step = normal <= 1 ? 1 : normal <= 2 ? 2 : normal <= 5 ? 5 : 10;
  return step * magnitude;
};

const niceDomain = (min: number, max: number, target = 4): {lo: number; hi: number; step: number} => {
  let low = min;
  let high = max;
  if (!Number.isFinite(low) || !Number.isFinite(high)) return {lo: 0, hi: 1, step: 0.25};
  if (high - low < 1e-9) {
    const pad = Math.abs(high) * 0.15 || 1;
    low -= pad;
    high += pad;
  }
  const step = niceStep(high - low, target);
  const lo = Math.floor(low / step + 1e-9) * step;
  const hi = Math.ceil(high / step - 1e-9) * step;
  return {lo, hi, step};
};

const yDomainFor = (values: number[], includeZero: boolean, target = 4) => {
  const low = Math.min(...values);
  const high = Math.max(...values);
  return niceDomain(includeZero ? Math.min(0, low) : low,
                    includeZero ? Math.max(0, high) : high, target);
};

const format = (value: number, step: number): string => {
  const decimals = step >= 1 ? 0 : Math.min(3, Math.ceil(-Math.log10(step)));
  const text = value.toFixed(decimals);
  return text === '-0' ? '0' : text;
};

const isConstant = (series: Series): boolean =>
  series.values.length >= 2 && series.values.every((value) => Math.abs(value - series.values[0]) < 1e-9);

const isMarker = (series: Series): boolean =>
  Boolean(series.x_values?.length) && series.x_values.every((value) => Math.abs(value - series.x_values[0]) < 1e-9);

/**
 * Monotone cubic (Fritsch–Carlson) interpolation: smooth, and never above/below
 * the samples, so the drawing cannot invent a value the narration does not claim.
 */
const smoothPath = (points: [number, number][]): string => {
  const n = points.length;
  if (n === 0) return '';
  if (n === 1) return `M${points[0][0].toFixed(1)} ${points[0][1].toFixed(1)}`;
  const increasing = points.every((point, index) => index === 0 || point[0] >= points[index - 1][0]);
  if (n === 2 || !increasing) {
    return points.map(([x, y], index) => `${index ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
  }
  const dx: number[] = [];
  const slope: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    const deltaX = points[i + 1][0] - points[i][0] || 1e-6;
    dx.push(deltaX);
    slope.push((points[i + 1][1] - points[i][1]) / deltaX);
  }
  const tangent: number[] = new Array(n).fill(0);
  tangent[0] = slope[0];
  tangent[n - 1] = slope[n - 2];
  for (let i = 1; i < n - 1; i++) {
    tangent[i] = slope[i - 1] * slope[i] <= 0 ? 0 : (slope[i - 1] + slope[i]) / 2;
  }
  for (let i = 0; i < n - 1; i++) {
    if (slope[i] === 0) {
      tangent[i] = 0;
      tangent[i + 1] = 0;
      continue;
    }
    const a = tangent[i] / slope[i];
    const b = tangent[i + 1] / slope[i];
    const length = Math.hypot(a, b);
    if (length > 3) {
      const scale = 3 / length;
      tangent[i] = scale * a * slope[i];
      tangent[i + 1] = scale * b * slope[i];
    }
  }
  let path = `M${points[0][0].toFixed(1)} ${points[0][1].toFixed(1)}`;
  for (let i = 0; i < n - 1; i++) {
    const handle = dx[i] / 3;
    const c1x = points[i][0] + handle;
    const c1y = points[i][1] + tangent[i] * handle;
    const c2x = points[i + 1][0] - handle;
    const c2y = points[i + 1][1] - tangent[i + 1] * handle;
    path += ` C${c1x.toFixed(1)} ${c1y.toFixed(1)} ${c2x.toFixed(1)} ${c2y.toFixed(1)}`
      + ` ${points[i + 1][0].toFixed(1)} ${points[i + 1][1].toFixed(1)}`;
  }
  return path;
};

type Chip = {x: number; y: number; w: number; h: number; text: string; color: string};

const overlaps = (a: Chip, b: Chip): boolean =>
  a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

const placeChips = (chips: Chip[], top: number, bottom: number): Chip[] => {
  const placed: Chip[] = [];
  for (const chip of chips) {
    const candidates = [chip, {...chip, y: chip.y + chip.h + 12}, {...chip, y: chip.y + (chip.h + 10) * 2}];
    let chosen: Chip | undefined;
    for (const candidate of candidates) {
      if (candidate.y < top - 2 || candidate.y + candidate.h > bottom + 2) continue;
      if (placed.some((other) => overlaps(candidate, other))) continue;
      chosen = candidate;
      break;
    }
    if (chosen) placed.push(chosen);
  }
  return placed;
};

const nearestSample = (series: Series[], x: number): {x: number; y: number; seriesIndex: number} | undefined => {
  let best: {x: number; y: number; seriesIndex: number; distance: number} | undefined;
  series.forEach((entry, seriesIndex) => {
    if (isConstant(entry)) return;
    const explicit = entry.x_values?.length === entry.values.length;
    entry.values.forEach((value, index) => {
      const sampleX = explicit ? entry.x_values[index] : index;
      const distance = Math.abs(sampleX - x);
      if (!best || distance < best.distance) best = {x: sampleX, y: value, seriesIndex, distance};
    });
  });
  return best;
};

export const ChartLayer: React.FC<{
  layer: Layer; theme: Theme; reveal: number; vertical: boolean; box?: Box;
  beat?: number; beats?: Beat[]; scene?: Scene; showAnnotations?: boolean;
}> = ({layer, theme, reveal, box, beat = 0, beats = [], scene, showAnnotations = true}) => {
  const series = layer.series.filter((s) => s.values.length >= 2);
  if (!series.length) {
    return <div style={{color: theme.muted, fontSize: 34}}>缺少数据，不能凭空绘制曲线</div>;
  }
  const regionAspect = box ? Math.max(0.7, Math.min(3.4, box.w / Math.max(1, box.h))) : 1000 / 640;
  const canvasWidth = Math.round(640 * regionAspect);
  const unit = Math.max(1, canvasWidth / 1000);
  const font = (size: number): number => Math.round(size * unit);

  const explicitX = series.every((s) => s.x_values && s.x_values.length === s.values.length);
  const dataSeries = series.filter((s) => !isConstant(s) && !isMarker(s));
  const xs = (dataSeries.length ? dataSeries : series).flatMap((s) => (explicitX ? s.x_values : s.values.map((_v, i) => i)));
  const ys = series.flatMap((s) => s.values);
  const xDomain = niceDomain(Math.min(...xs), Math.max(...xs), 4);
  const bars = layer.chart === 'bar';
  const scatter = layer.chart === 'scatter';
  const sortedX = [...new Set(xs)].sort((a, b) => a - b);
  const slot = bars && sortedX.length > 1
    ? Math.min(...sortedX.slice(1).map((value, index) => value - sortedX[index]))
    : xDomain.step;
  const padX = bars ? slot * 0.5 : xDomain.step * 0.5;
  const xMin = xDomain.lo - padX;
  const xMax = xDomain.hi + padX;
  const xTicks: number[] = [];
  for (let value = xDomain.lo; value <= xDomain.hi + xDomain.step * 1e-6; value += xDomain.step) {
    xTicks.push(Number(value.toFixed(6)));
  }

  // Bars start at zero, so derive their ticks from the same zero-based domain.
  // Otherwise a tight data range (for example 3–5) puts every tick in the
  // upper half while the bars themselves occupy the full plot from zero.
  const yDomain = yDomainFor(ys, bars, 4);
  const {lo, hi, step} = yDomain;
  const yTicks: number[] = [];
  for (let value = lo; value <= hi + step * 1e-6; value += step) yTicks.push(Number(value.toFixed(6)));
  const padY = bars ? (hi - lo) * 0.22 : step * 0.35;
  const yLo = bars ? Math.min(0, lo) : lo - padY;
  const yHi = hi + padY;

  const legendSeries = series.filter((s) => !isMarker(s) && !isConstant(s));
  const hasLegend = legendSeries.length > 1;
  const singleLabel = !hasLegend && series.length === 1 ? series[0].label : '';
  const legendRow = hasLegend ? font(42) : font(4);
  const panelRow = singleLabel ? font(40) : 0;
  const left = font(108);
  const right = font(44);
  const top = legendRow + panelRow + font(20);
  const bottom = font(116);
  const width = canvasWidth - left - right;
  const height = 640 - top - bottom;

  const xAt = (value: number): number => left + ((value - xMin) / (xMax - xMin)) * width;
  const yAt = (value: number): number => top + height - ((value - yLo) / (yHi - yLo)) * height;
  const colors = palette(layer);
  const baseline = yAt(Math.max(yLo, Math.min(yHi, 0)));
  const chips: Chip[] = [];
  const annotations: Annotation[] = showAnnotations
    ? (scene ? annotationsFor(scene, layer, beat, beats) : (layer.annotations || []))
    : [];
  const annotationXs = annotations
    .map((annotation) => nearestSample(series, annotation.x)?.x)
    .filter((value): value is number => value !== undefined);
  const highlight = layer.highlight?.length === 2
    ? layer.highlight
    : (bars && dataSeries.length === 1 && dataSeries[0].values.length === 2
        ? [sortedX[0], sortedX[1]] : []);

  return (
    <svg viewBox={`0 0 ${canvasWidth} 640`} width="100%" height="100%" style={{overflow: 'hidden'}}>
      <defs>
        {colors.map((color, index) => (
          <linearGradient key={`area-${index}`} id={`chart-area-${layer.id}-${index}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.36}/>
            <stop offset="100%" stopColor={color} stopOpacity={0.02}/>
          </linearGradient>
        ))}
        {colors.map((color, index) => (
          <linearGradient key={`bar-${index}`} id={`chart-bar-${layer.id}-${index}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={1}/>
            <stop offset="100%" stopColor={accentDeep[layer.color] || color} stopOpacity={0.92}/>
          </linearGradient>
        ))}
        <clipPath id={`chart-reveal-${layer.id}`}>
          <rect x={0} y={0} width={canvasWidth * (bars ? 1 : Math.max(0.001, Math.min(1, reveal)))}
            height={bars ? top + height + font(60) : height + font(60)}/>
        </clipPath>
        <filter id={`chart-glow-${layer.id}`} x="-20%" y="-30%" width="140%" height="160%">
          <feGaussianBlur stdDeviation="7" result="blur"/>
          <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>

      {highlight.length === 2 && <g>
        <rect x={xAt(Math.min(highlight[0], highlight[1]))} y={top}
          width={Math.max(2, Math.abs(xAt(highlight[0]) - xAt(highlight[1])))} height={height}
          fill={accent[layer.color] || '#6fe6ef'} opacity={0.07}/>
        {[Math.min(highlight[0], highlight[1]), Math.max(highlight[0], highlight[1])].map((value) =>
          <line key={`hl${value}`} x1={xAt(value)} y1={top} x2={xAt(value)} y2={top + height}
            stroke={accent[layer.color] || '#6fe6ef'} strokeOpacity={0.25}
            strokeDasharray={`${font(6)} ${font(6)}`}/>)}
      </g>}

      {yTicks.map((tick) => (
        <g key={`y${tick}`}>
          <line x1={left} y1={yAt(tick)} x2={left + width} y2={yAt(tick)}
            stroke={theme.grid} strokeOpacity={tick === 0 ? 0.34 : 0.12}
            strokeWidth={tick === 0 ? 2 : 1.5}/>
          <text x={left - font(18)} y={yAt(tick) + font(11)} textAnchor="end"
            fill={theme.muted} fontSize={font(28)}>{format(tick, step)}</text>
        </g>
      ))}

      <line x1={left} y1={top + height} x2={left + width} y2={top + height}
        stroke={theme.grid} strokeOpacity={0.42} strokeWidth={2}/>

      {(bars ? sortedX : xTicks).map((tick) => (
        <text key={`x${tick}`} x={xAt(tick)} y={top + height + font(38)} textAnchor="middle"
          fill={theme.muted} fontSize={font(27)}>{format(tick, bars ? 1 : xDomain.step)}</text>
      ))}

      <g clipPath={`url(#chart-reveal-${layer.id})`}>
        {series.map((s, sIndex) => {
          const color = colors[sIndex % colors.length];
          const deep = accentDeep[layer.color] || color;
          const xValues = explicitX ? s.x_values : s.values.map((_v, i) => i);
          const hasEquals = s.label.includes('=') || s.label.includes('＝');
          if (isMarker(s)) {
            const x = xAt(xValues[0]);
            const y = yAt(s.values[0]);
            const label = hasEquals ? s.label : `${s.label} ${format(s.values[0], step)}`;
            const labelWidth = measureText(label, font(26)) + font(24);
            const above = y - font(58) > top + font(4);
            return <g key={`marker-${s.label}`} opacity={Math.min(1, reveal * 1.3)}>
              <line x1={x} y1={y} x2={x} y2={top + height} stroke={color} strokeWidth={1.5}
                strokeDasharray={`${font(5)} ${font(6)}`} opacity={0.45}/>
              <circle cx={x} cy={y} r={font(15)} fill="none" stroke={color} strokeWidth={2} opacity={0.6}/>
              <circle cx={x} cy={y} r={font(8)} fill={color}/>
              <rect x={x + font(16)} y={above ? y - font(48) : y + font(16)} width={labelWidth}
                height={font(34)} rx={font(8)} fill={theme.surface} fillOpacity={0.94}
                stroke={`${color}66`} strokeWidth={1.5}/>
              <text x={x + font(27)} y={(above ? y - font(24) : y + font(40))} fill={color}
                fontSize={font(26)}>{label}</text>
            </g>;
          }
          if (isConstant(s)) {
            const y = yAt(s.values[0]);
            const label = hasEquals ? s.label : `${s.label} = ${format(s.values[0], step)}`;
            const labelWidth = measureText(label, font(26)) + font(20);
            return <g key={`ref-${s.label}`}>
              <line x1={left} y1={y} x2={left + width} y2={y} stroke={color} strokeWidth={2.5}
                strokeDasharray={`${font(10)} ${font(8)}`} opacity={0.7}/>
              <rect x={left + width - labelWidth} y={y - font(44)} width={labelWidth}
                height={font(34)} rx={font(8)} fill={theme.surface} fillOpacity={0.92}/>
              <text x={left + width - labelWidth + font(10)} y={y - font(20)} textAnchor="start"
                fill={color} fontSize={font(26)}>{label}</text>
            </g>;
          }
          const points = s.values.map((value, index) => [xAt(xValues[index]), yAt(value)] as [number, number]);
          if (bars) {
            const slotWidth = (width / Math.max(1, xValues.length)) * 0.68;
            const barWidth = Math.max(font(8), slotWidth / Math.max(1, dataSeries.length));
            const offset = dataSeries.indexOf(s) - (dataSeries.length - 1) / 2;
            return <g key={s.label}>
              {points.map(([x, y], index) => {
                const value = s.values[index];
                const grow = Math.max(0.02, Math.min(1, reveal));
                const full = Math.abs(baseline - y);
                const height2 = full * grow;
                const x0 = x + offset * barWidth - barWidth * 0.42;
                const y0 = value >= 0 ? baseline - height2 : baseline;
                const inside = value >= 0 && y0 - font(18) < top + font(6);
                const labelY = inside ? y0 + font(34) : (value >= 0 ? y0 - font(14) : y0 + height2 + font(28));
                return <g key={index}>
                  <rect x={x0} y={y0} width={barWidth} height={Math.max(2, height2)} rx={Math.min(8, barWidth / 4)}
                    fill={`url(#chart-bar-${layer.id}-${sIndex % colors.length})`}/>
                  <rect x={x0} y={y0} width={barWidth} height={Math.max(2, height2)} rx={Math.min(8, barWidth / 4)}
                    fill={deep} opacity={0.16}/>
                  <text x={x0 + barWidth / 2} y={labelY} textAnchor="middle"
                    fill={inside ? theme.backgroundBase : theme.text} fontWeight={inside ? 700 : 600}
                    fontSize={font(27)}>{format(value, step)}</text>
                </g>;
              })}
            </g>;
          }
          if (scatter && !layer.connect) {
            return <g key={s.label}>
              {points.map(([x, y], index) => <g key={index}>
                <circle cx={x} cy={y} r={font(16)} fill={color} opacity={0.16}/>
                <circle cx={x} cy={y} r={font(8)} fill={color}/>
              </g>)}
            </g>;
          }
          const path = smoothPath(points);
          const area = `${path} L${points[points.length - 1][0].toFixed(1)} ${top + height}`
            + ` L${points[0][0].toFixed(1)} ${top + height} Z`;
          return <g key={s.label}>
            {!scatter && <path d={area} fill={`url(#chart-area-${layer.id}-${sIndex % colors.length})`}/>}
            {scatter && layer.connect && <path d={`${path} Z`} fill={`${color}1f`} stroke={color}
              strokeWidth={font(5)} strokeLinejoin="round"/>}
            {!scatter && <path d={path} fill="none" stroke={color} strokeWidth={font(16)} opacity={0.10}
              strokeLinecap="round" strokeLinejoin="round" filter={`url(#chart-glow-${layer.id})`}/>}
            <path d={path} fill="none" stroke={color} strokeWidth={font(6)} strokeLinecap="round"
              strokeLinejoin="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - Math.min(1, reveal)}/>
            {points.map(([x, y], index) => <circle key={index} cx={x} cy={y} r={font(5)} fill={color}
              opacity={Math.min(1, reveal * 1.4)}/>)}
          </g>;
        })}
      </g>

      {bars && dataSeries.length === 1 && dataSeries[0].values.length === 2 && (() => {
        const vals = dataSeries[0].values;
        const x0 = xAt(sortedX[0]);
        const x1 = xAt(sortedX[1]);
        const y0 = yAt(vals[0]);
        const y1 = yAt(vals[1]);
        const topY = Math.min(y0, y1) - font(34);
        const delta = vals[1] - vals[0];
        return <g opacity={Math.min(1, Math.max(0, (reveal - 0.72) * 4))}>
          <path d={`M${x0} ${y0 - 10} L${x0} ${topY} L${x1} ${topY} L${x1} ${y1 - 10}`}
            fill="none" stroke={theme.muted} strokeWidth={2} strokeDasharray={`${font(6)} ${font(5)}`}/>
          <rect x={(x0 + x1) / 2 - font(62)} y={topY - font(32)} width={font(124)} height={font(32)} rx={font(8)}
            fill={theme.backgroundBase} fillOpacity={0.9}/>
          <text x={(x0 + x1) / 2} y={topY - font(8)} textAnchor="middle" fill={theme.muted}
            fontSize={font(24)}>{`Δ ${delta > 0 ? '+' : ''}${format(delta, step)}`}</text>
        </g>;
      })()}

      {annotations.map((annotation, index) => {
        const nearest = nearestSample(series, annotation.x);
        if (!nearest) return null;
        const x = xAt(nearest.x);
        const y = yAt(nearest.y);
        const s = series[nearest.seriesIndex];
        const value = formatValue(nearest.y, s?.unit || layer.unit || '');
        const [head, ...tail] = String(annotation.text || '').split(' · ');
        const big = /[0-9]/.test(head) ? head : value;
        const small = tail.join(' · ') || (head === big ? (s?.label || '') : head);
        // A point label, not a second insight card.  Both lines are measured at
        // the size they are drawn at; measuring at a different size is what let
        // the note overflow the card and sit on top of the number.
        const bigSize = font(20);
        const smallSize = font(15);
        const padX = font(10);
        const singleLine = !small;
        const boxW = Math.max(font(74), measureText(big, bigSize) + padX * 2,
                              measureText(small, smallSize) + padX * 2);
        const boxH = singleLine ? bigSize + font(12) : bigSize + smallSize + font(16);
        const above = y - boxH - font(24) > top + font(8);
        const bx = Math.max(left + 4, Math.min(left + width - boxW - 4, x - boxW / 2));
        const by = above ? y - boxH - font(16) : y + font(16);
        const color = colors[(nearest.seriesIndex >= 0 ? nearest.seriesIndex : index) % colors.length];
        const pulse = 0.5 + 0.5 * Math.sin(beat * 1.7 + 0.8);
        return <g key={`annotation-${index}`}>
          <line x1={x} y1={y} x2={x} y2={above ? by + boxH : by}
            stroke={color} strokeWidth={2} strokeDasharray={`${font(5)} ${font(5)}`} opacity={0.7}/>
          <line x1={x} y1={y} x2={left + width} y2={y} stroke={color} strokeWidth={1}
            strokeDasharray={`${font(3)} ${font(7)}`} opacity={0.22}/>
          <circle cx={x} cy={y} r={font(18 + 4 * pulse)} fill="none" stroke={color} strokeWidth={2}
            opacity={0.28 + 0.25 * pulse}/>
          <circle cx={x} cy={y} r={font(9)} fill={color}/>
          <g>
            <rect x={bx} y={by} width={boxW} height={boxH} rx={font(6)}
              fill={theme.backgroundBase} fillOpacity={0.88} stroke={`${color}66`} strokeWidth={1.5}/>
            <rect x={bx} y={by} width={font(4)} height={boxH} rx={font(2)} fill={color}/>
            <text x={bx + padX} y={by + bigSize + font(4)} fill={color} fontSize={bigSize}
              fontWeight={800}>{big}</text>
            {!singleLine && <text x={bx + padX} y={by + bigSize + smallSize + font(9)} fill={theme.muted}
              fontSize={smallSize}>{small}</text>}
          </g>
        </g>;
      })}

      {!bars && dataSeries.map((s) => {
        const color = colors[series.indexOf(s) % colors.length];
        const xValues = explicitX ? s.x_values : s.values.map((_v, i) => i);
        const first: [number, number] = [xAt(xValues[0]), yAt(s.values[0])];
        const last: [number, number] = [xAt(xValues[xValues.length - 1]), yAt(s.values[s.values.length - 1])];
        const lastText = format(s.values[s.values.length - 1], step);
        const lastWidth = measureText(lastText, font(27)) + font(20);
        const lastX = xValues[xValues.length - 1];
        const annotatedLast = annotationXs.some((value) => Math.abs(value - lastX) < 1e-9);
        const firstX = xValues[0];
        const annotatedFirst = annotationXs.some((value) => Math.abs(value - firstX) < 1e-9);
        if ((s.values.length >= 4 || scatter) && !annotatedFirst) {
          const firstText = format(s.values[0], step);
          const firstWidth = measureText(firstText, font(27)) + font(20);
          chips.push({x: first[0] + font(12), y: first[1] - font(40), w: firstWidth,
                      h: font(34), text: firstText, color});
        }
        if (!annotatedLast) {
          chips.push({x: last[0] - lastWidth - font(12), y: last[1] - font(40), w: lastWidth,
                      h: font(34), text: lastText, color});
        }
        return null;
      })}

      {placeChips(chips, top + font(2), top + height - font(6)).map((chip, index) => (
        <g key={`${chip.text}-${index}`}>
          <rect x={chip.x} y={chip.y} width={chip.w} height={chip.h} rx={font(8)}
            fill={theme.surface} fillOpacity={0.92} stroke={`${chip.color}55`} strokeWidth={1.5}/>
          <text x={chip.x + font(10)} y={chip.y + font(25)} fill={chip.color}
            fontSize={font(27)}>{chip.text}</text>
        </g>
      ))}

      <text x={left} y={640 - font(40)} fill={theme.muted} fontSize={font(28)}>
        {`${layer.axis || (explicitX ? 'x' : '步骤')} →`}
      </text>
      {layer.unit && <text x={font(30)} y={top + height / 2} fill={theme.muted} fontSize={font(26)}
        textAnchor="middle" transform={`rotate(-90 ${font(30)} ${top + height / 2})`}>
        {`${layer.unit} ↑`}
      </text>}

      {singleLabel && <g>
        <rect x={left} y={font(2)} width={measureText(singleLabel, font(29)) + font(28)}
          height={font(34)} rx={font(8)} fill={theme.surface} fillOpacity={0.78}/>
        <text x={left + font(12)} y={font(26)} fill={theme.text} fontSize={font(29)}
          fontWeight={600}>{singleLabel}</text>
      </g>}

      {hasLegend && (() => {
        let cursor = 0;
        return <g transform={`translate(${left}, ${font(8)})`}>
          {legendSeries.map((s) => {
            const color = colors[series.indexOf(s) % colors.length];
            const label = s.label.length > 14 ? `${s.label.slice(0, 14)}…` : s.label;
            const chipWidth = font(24);
            const itemWidth = chipWidth + font(14) + measureText(label, font(29)) + font(30);
            const x = cursor;
            cursor += itemWidth;
            return <g key={s.label} transform={`translate(${x}, 0)`}>
              <rect width={chipWidth} height={chipWidth} y={-font(2)} fill={color} rx={font(5)}/>
              <text x={font(36)} y={font(23)} fill={theme.text} fontSize={font(29)}>{label}</text>
            </g>;
          })}
        </g>;
      })()}

      {layer.source_note && <text x={left + width} y={640 - font(8)} textAnchor="end"
        fill={theme.faint} fontSize={font(22)}>{layer.source_note}</text>}
    </svg>
  );
};
