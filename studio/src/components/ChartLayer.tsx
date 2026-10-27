import React from 'react';
import type {Layer, Series} from '../types';
import type {Theme} from '../theme';
import {accent, accentDeep} from '../theme';
import type {Box} from '../Stage';
import {measureText} from '../layouts';

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

/** Trim trailing zeros without turning 1000 into 1k: these are axis labels, not prose. */
const format = (value: number, step: number): string => {
  const decimals = step >= 1 ? 0 : Math.min(3, Math.ceil(-Math.log10(step)));
  const text = value.toFixed(decimals);
  return text === '-0' ? '0' : text;
};

const isConstant = (series: Series): boolean =>
  series.values.length >= 2 && series.values.every((value) => Math.abs(value - series.values[0]) < 1e-9);

/** All samples at the same x: a marker for one instant, not a line. */
const isMarker = (series: Series): boolean =>
  Boolean(series.x_values?.length) && series.x_values.every((value) => Math.abs(value - series.x_values[0]) < 1e-9);

/**
 * Monotone cubic (Fritsch–Carlson) interpolation.
 *
 * A quadratic drawn through eight samples as straight segments looks like a
 * polygon, not a parabola.  A plain Catmull-Rom spline would overshoot and invent
 * values the narration does not claim, so the tangents are limited to keep the
 * curve monotone between samples: smooth, and never above/below the data.
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

type Label = {x: number; y: number; text: string; anchor: 'start' | 'end'; color: string};
type Chip = {x: number; y: number; w: number; h: number; text: string; color: string};

const overlaps = (a: Chip, b: Chip): boolean =>
  a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

/**
 * Place value chips without covering each other.
 *
 * V1 drew a label for the first and last value of every series at fixed offsets;
 * with two series and a reference line they landed on top of each other and on the
 * legend.  Here a chip that collides is nudged vertically inside the plot, and one
 * that cannot fit is dropped rather than drawn over something else.
 */
const placeChips = (chips: Chip[], top: number, bottom: number): Chip[] => {
  const placed: Chip[] = [];
  for (const chip of chips) {
    // Prefer above the point; fall back to below it; then nudge; drop if nothing fits.
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

export const ChartLayer: React.FC<{layer: Layer; theme: Theme; reveal: number; vertical: boolean; box?: Box}> =
({layer, theme, reveal, vertical, box}) => {
  const series = layer.series.filter((s) => s.values.length >= 2);
  if (!series.length) {
    return <div style={{color: theme.muted, fontSize: 26}}>缺少数据，不能凭空绘制曲线</div>;
  }
  // Canvas matches the region's aspect ratio so a wide, short box is not
  // letterboxed into a small chart with large empty margins.
  const regionAspect = box ? Math.max(0.7, Math.min(3.4, box.w / Math.max(1, box.h))) : 1000 / 640;
  const canvasWidth = Math.round(640 * regionAspect);
  const unit = Math.max(1, canvasWidth / 1000);
  const font = (size: number): number => Math.round(size * unit);

  const explicitX = series.every((s) => s.x_values && s.x_values.length === s.values.length);
  const dataSeries = series.filter((s) => !isConstant(s) && !isMarker(s));
  const markers = series.filter(isMarker);
  const references = series.filter((s) => isConstant(s) && !isMarker(s));
  const xs = (dataSeries.length ? dataSeries : series).flatMap((s) => (explicitX ? s.x_values : s.values.map((_v, i) => i)));
  const ys = series.flatMap((s) => s.values);
  const rawXMin = Math.min(...xs);
  const rawXMax = Math.max(...xs);
  const xDomain = niceDomain(rawXMin, rawXMax, 4);
  const bars = layer.chart === 'bar';
  const scatter = layer.chart === 'scatter';
  // Bars sit at their x values, so the axis needs half a slot of padding on each
  // side; otherwise the first and last bar are cut in half by the plot edge (and
  // their value labels by the reveal mask).
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

  const yDomain = niceDomain(Math.min(...ys), Math.max(...ys), 4);
  const {lo, hi, step} = yDomain;
  const yTicks: number[] = [];
  for (let value = lo; value <= hi + step * 1e-6; value += step) yTicks.push(Number(value.toFixed(6)));
  // Bars keep the axis edge at zero but need headroom for the value label above the
  // tallest bar; without it the label is clipped by the reveal mask.
  const padY = bars ? (hi - lo) * 0.22 : step * 0.35;
  const yLo = bars ? Math.min(0, lo) : lo - padY;
  const yHi = hi + padY;

  const legendSeries = series.filter((s) => !isMarker(s) && !isConstant(s));
  const hasLegend = legendSeries.length > 1;
  const legendRow = font(30) + font(10);
  const left = font(104);
  const right = font(46);
  const top = (hasLegend ? legendRow + font(18) : font(14)) + font(16);
  const bottom = font(118);
  const width = canvasWidth - left - right;
  const height = 640 - top - bottom;

  const xAt = (value: number): number => left + ((value - xMin) / (xMax - xMin)) * width;
  const yAt = (value: number): number => top + height - ((value - yLo) / (yHi - yLo)) * height;
  const colors = palette(layer);
  const baseline = yAt(Math.max(yLo, Math.min(yHi, 0)));
  const chips: Chip[] = [];

  return (
    <svg viewBox={`0 0 ${canvasWidth} 640`} width="100%" height="100%" style={{overflow: 'hidden'}}>
      <defs>
        {colors.map((color, index) => (
          <linearGradient key={`area-${index}`} id={`chart-area-${layer.id}-${index}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.30}/>
            <stop offset="100%" stopColor={color} stopOpacity={0}/>
          </linearGradient>
        ))}
        {/* Bars need a fill that is still a bar at the baseline: fading to zero
            opacity made every bar look like it was dissolving into the axis. */}
        {colors.map((color, index) => (
          <linearGradient key={`bar-${index}`} id={`chart-bar-${layer.id}-${index}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={1}/>
            <stop offset="100%" stopColor={accentDeep[layer.color] || color} stopOpacity={0.95}/>
          </linearGradient>
        ))}
        <clipPath id={`chart-reveal-${layer.id}`}>
          {/* Bars grow from the baseline instead of being wiped sideways: a
              horizontal cut through a bar reads as a rendering fault. */}
          <rect x={0} y={0} width={canvasWidth * (bars ? 1 : Math.max(0.001, Math.min(1, reveal)))}
            height={bars ? top + height + font(60) : height + font(60)}/>
        </clipPath>
      </defs>

      {/* Horizontal grid only: vertical lines add noise without helping to read a trend. */}
      {yTicks.map((tick) => (
        <g key={`y${tick}`}>
          <line x1={left} y1={yAt(tick)} x2={left + width} y2={yAt(tick)}
            stroke={theme.grid} strokeOpacity={tick === 0 ? 0.32 : 0.11}
            strokeWidth={tick === 0 ? 2 : 1.5}/>
          <text x={left - font(16)} y={yAt(tick) + font(9)} textAnchor="end"
            fill={theme.muted} fontSize={font(24)}>{format(tick, step)}</text>
        </g>
      ))}

      {/* Bars grow from zero, so the zero line is the baseline they are read against. */}
      <line x1={left} y1={top + height} x2={left + width} y2={top + height}
        stroke={theme.grid} strokeOpacity={0.4} strokeWidth={2}/>

      {/* x ticks: V1 dropped them entirely, which left the horizontal axis unreadable.
          A bar chart shows only its categories (0.5 between two bars is noise). */}
      {(bars ? sortedX : xTicks).map((tick) => (
        <text key={`x${tick}`} x={xAt(tick)} y={top + height + font(34)} textAnchor="middle"
          fill={theme.muted} fontSize={font(23)}>{format(tick, bars ? 1 : xDomain.step)}</text>
      ))}

      <g clipPath={`url(#chart-reveal-${layer.id})`}>
        {series.map((s, sIndex) => {
          const color = colors[sIndex % colors.length];
          const deep = accentDeep[layer.color] || color;
          const xValues = explicitX ? s.x_values : s.values.map((_v, i) => i);
          const hasEquals = s.label.includes('=') || s.label.includes('＝');
          if (isMarker(s)) {
            // Every sample at one x: this is a marker for "the current point", not a
            // line.  Drawn as a ring plus a labelled dot, which is how an editor
            // annotates a value on a curve.
            const x = xAt(xValues[0]);
            const y = yAt(s.values[0]);
            const label = hasEquals ? s.label : `${s.label} ${format(s.values[0], step)}`;
            const labelWidth = measureText(label, font(22)) + font(22);
            const above = y - font(52) > top + font(4);
            return <g key={`marker-${s.label}`} opacity={Math.min(1, reveal * 1.3)}>
              <line x1={x} y1={y} x2={x} y2={top + height} stroke={color} strokeWidth={1.5}
                strokeDasharray={`${font(5)} ${font(6)}`} opacity={0.45}/>
              <circle cx={x} cy={y} r={font(13)} fill="none" stroke={color} strokeWidth={2} opacity={0.6}/>
              <circle cx={x} cy={y} r={font(7)} fill={color}/>
              <rect x={x + font(14)} y={above ? y - font(44) : y + font(14)} width={labelWidth}
                height={font(30)} rx={font(6)} fill={theme.surface} fillOpacity={0.94}
                stroke={`${color}66`} strokeWidth={1.5}/>
              <text x={x + font(24)} y={(above ? y - font(22) : y + font(36))} fill={color}
                fontSize={font(22)}>{label}</text>
            </g>;
          }
          if (isConstant(s)) {
            // A flat series across the x range is a reference level (a target, a
            // threshold), not data: drawing it as a data line made it look like a
            // second measurement.
            const y = yAt(s.values[0]);
            const label = hasEquals ? s.label : `${s.label} = ${format(s.values[0], step)}`;
            const labelWidth = measureText(label, font(22)) + font(18);
            return <g key={`ref-${s.label}`}>
              <line x1={left} y1={y} x2={left + width} y2={y} stroke={color} strokeWidth={2.5}
                strokeDasharray={`${font(10)} ${font(8)}`} opacity={0.7}/>
              <rect x={left + width - labelWidth} y={y - font(38)} width={labelWidth}
                height={font(30)} rx={font(6)} fill={theme.surface} fillOpacity={0.92}/>
              <text x={left + width - labelWidth + font(9)} y={y - font(16)} textAnchor="start"
                fill={color} fontSize={font(22)}>{label}</text>
            </g>;
          }
          const points = s.values.map((value, index) => [xAt(xValues[index]), yAt(value)] as const) as [number, number][];
          if (bars) {
            const slot = (width / Math.max(1, xValues.length)) * 0.68;
            const barWidth = Math.max(font(8), slot / Math.max(1, dataSeries.length));
            const offset = dataSeries.indexOf(s) - (dataSeries.length - 1) / 2;
            return <g key={s.label}>
              {points.map(([x, y], index) => {
                const value = s.values[index];
                // Bars grow from the baseline; the label fades in with the growth so a
                // number never floats above a bar that has not reached it yet.
                const grow = Math.max(0.02, Math.min(1, reveal));
                const full = Math.abs(baseline - y);
                const height2 = full * grow;
                const x0 = x + offset * barWidth - barWidth * 0.42;
                const y0 = value >= 0 ? baseline - height2 : baseline;
                // A tall bar has no room for a label above it: put the number inside
                // the bar instead of letting the reveal mask clip it.
                const inside = value >= 0 && y0 - font(16) < top + font(6);
                const labelY = inside ? y0 + font(30) : (value >= 0 ? y0 - font(12) : y0 + height2 + font(24));
                return <g key={index}>
                  <rect x={x0} y={y0} width={barWidth} height={Math.max(2, height2)} rx={Math.min(6, barWidth / 4)}
                    fill={`url(#chart-bar-${layer.id}-${sIndex % colors.length})`}/>
                  <rect x={x0} y={y0} width={barWidth} height={Math.max(2, height2)} rx={Math.min(6, barWidth / 4)}
                    fill={deep} opacity={0.18}/>
                  <text x={x0 + barWidth / 2} y={labelY} textAnchor="middle"
                    fill={inside ? theme.backgroundBase : theme.text} fontWeight={inside ? 700 : 500}
                    fontSize={font(23)}>{format(value, step)}</text>
                </g>;
              })}
            </g>;
          }
          if (scatter && !layer.connect) {
            return <g key={s.label}>
              {points.map(([x, y], index) => <g key={index}>
                <circle cx={x} cy={y} r={font(13)} fill={color} opacity={0.18}/>
                <circle cx={x} cy={y} r={font(6.5)} fill={color}/>
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
            <path d={path} fill="none" stroke={color} strokeWidth={font(5.5)} strokeLinecap="round"
              strokeLinejoin="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - Math.min(1, reveal)}/>
            {points.map(([x, y], index) => <circle key={index} cx={x} cy={y} r={font(4.5)} fill={color}
              opacity={Math.min(1, reveal * 1.4)}/>)}
          </g>;
        })}
      </g>

      {/* Only the first and last value get a label: labelling every point is a
          spreadsheet, not an explainer.  A constant reference series is skipped
          here because it already prints its own value. */}
      {!bars && dataSeries.map((s) => {
        const color = colors[series.indexOf(s) % colors.length];
        const xValues = explicitX ? s.x_values : s.values.map((_v, i) => i);
        const first: [number, number] = [xAt(xValues[0]), yAt(s.values[0])];
        const last: [number, number] = [xAt(xValues[xValues.length - 1]), yAt(s.values[s.values.length - 1])];
        const lastText = format(s.values[s.values.length - 1], step);
        const lastWidth = measureText(lastText, font(23)) + font(18);
        if (s.values.length >= 4) {
          const firstText = format(s.values[0], step);
          const firstWidth = measureText(firstText, font(23)) + font(18);
          chips.push({x: first[0] + font(12), y: first[1] - font(36), w: firstWidth,
                      h: font(30), text: firstText, color});
        }
        chips.push({x: last[0] - lastWidth - font(12), y: last[1] - font(36), w: lastWidth,
                    h: font(30), text: lastText, color});
        return null;
      })}

      {placeChips(chips, top + font(2), top + height - font(6)).map((chip, index) => (
        <g key={`${chip.text}-${index}`}>
          <rect x={chip.x} y={chip.y} width={chip.w} height={chip.h} rx={font(6)}
            fill={theme.surface} fillOpacity={0.92} stroke={`${chip.color}55`} strokeWidth={1.5}/>
          <text x={chip.x + font(9)} y={chip.y + font(22)} fill={chip.color}
            fontSize={font(23)}>{chip.text}</text>
        </g>
      ))}

      {/* Axis titles: what the axes mean, in words, on their own row so they never
          collide with a tick label.  The vertical quantity is rotated next to the y
          axis, which is how a printed chart labels it. */}
      <text x={left} y={640 - font(44)} fill={theme.muted} fontSize={font(24)}>
        {`${layer.axis || (explicitX ? 'x' : '步骤')} →`}
      </text>
      {layer.unit && <text x={font(26)} y={top + height / 2} fill={theme.muted} fontSize={font(22)}
        textAnchor="middle" transform={`rotate(-90 ${font(26)} ${top + height / 2})`}>
        {`${layer.unit} ↑`}
      </text>}

      {hasLegend && (() => {
        let cursor = 0;
        return <g transform={`translate(${left}, ${font(4)})`}>
          {legendSeries.map((s) => {
            const color = colors[series.indexOf(s) % colors.length];
            const label = s.label.length > 14 ? `${s.label.slice(0, 14)}…` : s.label;
            const chipWidth = font(22);
            const itemWidth = chipWidth + font(12) + measureText(label, font(25)) + font(26);
            const x = cursor;
            cursor += itemWidth;
            return <g key={s.label} transform={`translate(${x}, 0)`}>
              <rect width={chipWidth} height={chipWidth} y={0} fill={color} rx={font(4)}/>
              <text x={font(32)} y={font(20)} fill={theme.text} fontSize={font(25)}>{label}</text>
            </g>;
          })}
        </g>;
      })()}

      {layer.source_note && <text x={left + width} y={640 - font(6)} textAnchor="end"
        fill={theme.faint} fontSize={font(19)}>{layer.source_note}</text>}
    </svg>
  );
};
