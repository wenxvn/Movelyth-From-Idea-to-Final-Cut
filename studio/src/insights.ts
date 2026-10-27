import type {Annotation, Layer, Scene} from './types';

/**
 * V3: the picture has to change when the sentence changes.
 *
 * A 25-second shot with one entrance animation is a still image with a slow
 * zoom.  Instead of asking the director model for more animation primitives, we
 * derive 2–4 "coverage beats" from the real TTS timeline (sentence starts, then
 * beat anchors when the script provides them) and let every beat choose:
 *
 *   - which data point is the current subject (the insight card),
 *   - where the camera looks (CameraRig),
 *   - which annotation is on screen.
 *
 * Everything is a pure function of props and frame, so renders stay deterministic.
 */

export type Beat = {start: number; end: number};

export type ChartPoint = {
  seriesIndex: number;
  x: number;
  y: number;
  value: number;
  label: string;
  detail: string;
  marker?: boolean;
};

export type Insight = {
  value: string;
  label: string;
  detail: string;
  kind: 'chart' | 'diagram' | 'timeline' | 'text' | 'procedural';
  point?: ChartPoint;
  layerId?: string;
};

const clamp = (value: number): number => Math.max(0, Math.min(1, value));

export const unitSuffix = (unit: string): string =>
  unit && unit.length <= 3 && !/\s/.test(unit) ? unit : '';

export const formatValue = (value: number, unit = ''): string => {
  if (!Number.isFinite(value)) return '—';
  const suffix = unitSuffix(unit);
  const magnitude = Math.abs(value);
  if (magnitude < 1e-12) return `0${suffix}`;
  let text: string;
  if (magnitude >= 1000) text = value.toFixed(0);
  else if (magnitude >= 100) text = value.toFixed(1).replace(/\.0$/, '');
  else if (magnitude >= 1) text = value.toFixed(2).replace(/\.?0+$/, '');
  else if (magnitude >= 0.01) text = value.toFixed(3).replace(/\.?0+$/, '');
  else text = value.toExponential(1);
  return suffix ? `${text}${suffix}` : text;
};

/** A value written inside a label such as "当前点 w=0, L=5" or "初始预测 = 0". */
const valueFromLabel = (label: string): string => {
  const match = label.match(/[=＝]\s*(-?\d+(?:\.\d+)?)\s*([^\s,，;；]*)/);
  if (!match) return '';
  return `${match[1]}${match[2] || ''}`;
};

const isConstant = (values: number[]): boolean =>
  values.length >= 2 && values.every((value) => Math.abs(value - values[0]) < 1e-9);

const isMarker = (layer: Layer, index: number): boolean => {
  const series = layer.series[index];
  if (!series?.x_values?.length) return false;
  return series.x_values.every((value) => Math.abs(value - series.x_values[0]) < 1e-9);
};

/**
 * Sentence-level beats from caption pages.
 *
 * Captions are already page-level and carry real word boundaries.  A gap of more
 * than 0.18 s between pages is a sentence boundary (the separator between pages
 * inside a sentence is 0–0.15 s); grouping pages by that gap recovers sentences
 * without a second alignment pass.  Long scenes are then grouped into 2–4 beats of
 * roughly equal duration, which is the editing rhythm an editor would use.
 */
export const sceneBeats = (scene: Scene): Beat[] => {
  const duration = Math.max(0.5, scene.duration || scene.frames / 30);
  const anchors = (scene.beat_times || [])
    .map((beat) => beat.at)
    .filter((value) => Number.isFinite(value) && value > 0.2 && value < duration - 0.2);
  if (anchors.length >= 2) {
    const starts = [0, ...anchors.sort((a, b) => a - b)];
    return starts.map((start, index) => ({
      start,
      end: index + 1 < starts.length ? starts[index + 1] : duration,
    }));
  }
  const pages = [...(scene.captions || [])].sort((a, b) => a.start - b.start);
  if (!pages.length) {
    const target = duration > 14 ? 3 : 2;
    return Array.from({length: target}, (_v, index) => ({
      start: (duration / target) * index,
      end: (duration / target) * (index + 1),
    }));
  }
  const sentences: {start: number; end: number}[] = [];
  for (const page of pages) {
    const previous = sentences[sentences.length - 1];
    if (previous && page.start - previous.end <= 0.18) {
      previous.end = Math.max(previous.end, page.end);
    } else {
      sentences.push({start: page.start, end: page.end});
    }
  }
  // Start the first beat at the scene start so the opening still has a subject.
  if (sentences.length) sentences[0] = {...sentences[0], start: 0};
  const target = duration > 22 ? 4 : duration > 14 ? 3 : duration > 8 ? 2 : 1;
  if (sentences.length <= target) {
    return sentences.map((sentence, index) => ({
      start: sentence.start,
      end: index + 1 < sentences.length ? sentences[index + 1].start : duration,
    }));
  }
  // Group consecutive sentences so each beat is roughly duration/target long.
  const groups: {start: number; end: number}[] = [];
  const wanted = duration / target;
  let begin = sentences[0].start;
  let last = sentences[0].end;
  for (let index = 1; index < sentences.length; index++) {
    const sentence = sentences[index];
    const isLast = index === sentences.length - 1;
    if ((last - begin >= wanted * 0.82 || isLast) && groups.length < target - 1) {
      groups.push({start: begin, end: sentence.start});
      begin = sentence.start;
    }
    last = sentence.end;
  }
  groups.push({start: begin, end: duration});
  return groups.map((group, index) => ({
    start: group.start,
    end: index + 1 < groups.length ? groups[index + 1].start : duration,
  }));
};

export const activeBeat = (beats: Beat[], time: number): number => {
  for (let index = 0; index < beats.length; index++) {
    if (time < beats[index].end) return index;
  }
  return Math.max(0, beats.length - 1);
};

/** Normalised progress inside one beat; used for the camera and card entrances. */
export const beatProgress = (beat: Beat | undefined, time: number): number => {
  if (!beat) return 1;
  return clamp((time - beat.start) / Math.max(0.001, beat.end - beat.start));
};

/** All real data points a chart can honestly annotate, in a story order. */
export const chartPoints = (layer: Layer): ChartPoint[] => {
  const markersOut: ChartPoint[] = [];
  const points: ChartPoint[] = [];
  layer.series.forEach((series, seriesIndex) => {
    if (!series.values.length) return;
    const explicit = series.x_values?.length === series.values.length;
    const xs = explicit ? series.x_values : series.values.map((_v, i) => i);
    const unit = series.unit || '';
    if (isMarker(layer, seriesIndex)) {
      const value = series.values[0];
      markersOut.push({
        seriesIndex, x: xs[0], y: value, value,
        label: series.label,
        detail: valueFromLabel(series.label) ? '当前关注点' : '标记点',
        marker: true,
      });
      return;
    }
    if (isConstant(series.values)) return;
    const first = series.values[0];
    const last = series.values[series.values.length - 1];
    let minIndex = 0;
    let maxIndex = 0;
    series.values.forEach((value, index) => {
      if (value < series.values[minIndex]) minIndex = index;
      if (value > series.values[maxIndex]) maxIndex = index;
    });
    const add = (index: number, detail: string) => {
      const value = series.values[index];
      points.push({
        seriesIndex, x: xs[index], y: value, value,
        label: series.label,
        detail,
        marker: false,
      });
    };
    add(0, '起点');
    add(minIndex, '最低点');
    add(last > first ? maxIndex : minIndex, '关键点');
    add(series.values.length - 1, '终点');
  });
  return [...markersOut, ...points];
};

/** The chart layer that owns the main visual, if there is one. */
const mainChart = (scene: Scene): Layer | undefined =>
  scene.layers.find((layer) => layer.type === 'chart' && (layer.region === 'main' || layer.region === 'side'));

/** The diagram/timeline step that the current beat is about. */
const stepFor = (scene: Scene, beatIndex: number, beats: Beat[]): {value: string; label: string; detail: string} | undefined => {
  const layer = scene.layers.find((item) => (item.type === 'timeline' || item.type === 'diagram')
    && (item.steps.length || item.nodes.length));
  if (!layer) return undefined;
  const items = layer.steps.length ? layer.steps : layer.nodes.map((node) => node.label);
  if (!items.length) return undefined;
  const active = Math.min(items.length - 1, Math.round((beatIndex / Math.max(1, beats.length - 1)) * (items.length - 1)));
  const raw = items[active];
  // Diagram node labels often read "偏差 −2、−4": the number is the metric, the
  // word before the first space is the label.  A step label has no number.
  const match = raw.match(/^(.{1,8}?)\s+([−+\-]?\d[\d.、，,\s−+\-]*)$/);
  if (match) return {value: match[2].trim(), label: match[1], detail: scene.heading};
  return {value: raw, label: layer.steps.length ? '当前步骤' : '关键节点', detail: scene.heading};
};

const parseMath = (scene: Scene): {value: string; label: string} | undefined => {
  const layer = scene.layers.find((item) => item.type === 'math' && /[=＝]/.test(item.text));
  if (!layer) return undefined;
  const [left, ...rest] = layer.text.split(/[=＝]/);
  const right = rest.join('=');
  if (!left.trim() || !right.trim()) return undefined;
  return {label: left.trim().slice(0, 18), value: right.trim().slice(0, 16)};
};

/**
 * One insight per beat.  Explicit director fields win; otherwise the card is
 * derived from the real data so it can never claim a number the chart does not
 * contain.
 */
export const insightFor = (scene: Scene, beatIndex: number, beats: Beat[]): Insight | undefined => {
  const explicitValue = (scene.metric || '').trim();
  const explicitTakeaway = (scene.takeaway || '').trim();
  if (explicitValue || explicitTakeaway) {
    const chart = mainChart(scene);
    const point = chart ? chartPoints(chart)[beatIndex % Math.max(1, chartPoints(chart).length)] : undefined;
    return {
      value: explicitValue || (point ? formatValue(point.value, '') : '—'),
      label: explicitTakeaway || scene.labels[0] || scene.heading,
      detail: scene.labels[1] || scene.labels.find((label) => label !== explicitTakeaway) || scene.heading,
      kind: point ? 'chart' : 'text',
      point,
      layerId: chart?.id,
    };
  }
  const chart = mainChart(scene);
  if (chart) {
    const points = chartPoints(chart);
    if (points.length) {
      // A marker series is the "current point" the narration is standing on;
      // keep it as the subject for the whole shot instead of jumping to the
      // minimum at the last beat (the sentence is still about "here").
      const point = points.find((item) => item.marker) || points[beatIndex % points.length];
      const unit = chart.series[point.seriesIndex]?.unit || chart.unit || '';
      if (point.marker) {
        const w = point.label.match(/w\s*[=＝]\s*(-?[\d.]+)/i)?.[1];
        const loss = point.label.match(/L\s*[=＝]\s*(-?[\d.]+)/i)?.[1];
        return {
          value: formatValue(point.value, unit),
          label: '当前状态',
          detail: [w ? `w = ${w}` : '', loss ? `L = ${loss}` : ''].filter(Boolean).join(' · ') || point.label,
          kind: 'chart', point, layerId: chart.id,
        };
      }
      return {
        value: formatValue(point.value, unit),
        label: point.label || '数据',
        detail: point.detail,
        kind: 'chart',
        point,
        layerId: chart.id,
      };
    }
  }
  const step = stepFor(scene, beatIndex, beats);
  if (step) return {...step, kind: 'timeline'};
  const math = parseMath(scene);
  if (math) return {...math, detail: explicitTakeaway || scene.heading, kind: 'text'};
  const emphasis = (scene.emphasis || []).find(Boolean);
  const first = (scene.labels[0] || '').slice(0, 12);
  const second = scene.labels.find((label) => label !== first) || scene.heading;
  return {
    value: emphasis || first || '—',
    label: second,
    detail: scene.takeaway || scene.heading,
    kind: 'procedural',
  };
};

/** Annotations the director wrote, or one generated for the active beat. */
export const annotationsFor = (scene: Scene, layer: Layer, beatIndex: number, beats: Beat[]): Annotation[] => {
  if (layer.annotations?.length) return layer.annotations;
  if (layer.type !== 'chart') return [];
  // Bars already print their value on every bar; an extra callout tag collided
  // with the value label ("0.313L") and read as a rendering fault.
  if (layer.chart === 'bar') return [];
  // The split (diagram) layout already has an Insight card in the left column;
  // drawing a second callout on the plot duplicated the same number.  Full-width
  // charts keep the point callout because there is no card in the column.
  if (scene.layout === 'diagram') return [];
  // A marker series already labels itself ("当前点 w=0, L=5"); adding an auto
  // annotation on top of it drew two cards over the same point.
  if (layer.series.some((series, index) => isMarker(layer, index))) return [];
  const points = chartPoints(layer);
  if (!points.length) return [];
  const point = points[beatIndex % points.length];
  return [{x: point.x, text: `${formatValue(point.value, layer.series[point.seriesIndex]?.unit || layer.unit || '')} · ${point.detail}`}];
};
