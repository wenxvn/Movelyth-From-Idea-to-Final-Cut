export type Color = 'cyan' | 'amber' | 'coral' | 'mint';
export type VisualKind = 'matrix' | 'vectors' | 'projection' | 'wave' | 'network' | 'image_layers' | 'orbit';
export type LayerKind = 'text' | 'shape' | 'math' | 'chart' | 'diagram' | 'image' | 'procedural';
export type Region = 'main' | 'side' | 'top' | 'bottom' | 'annotation' | 'full';
export type LayoutKind = 'immersive' | 'diagram' | 'compare';
export type ActionKind = 'appear' | 'fade' | 'move' | 'scale' | 'rotate' | 'highlight' | 'draw' | 'morph';
export type ShapeKind = 'point' | 'line' | 'rect' | 'circle' | 'arrow' | 'polygon' | 'bracket';
export type ChartKind = 'line' | 'bar' | 'scatter';
export type StyleName = 'minimal' | 'tech' | 'documentary';

export type Series = {label: string; values: number[]; unit: string};
export type DiagramNode = {id: string; label: string; x: number; y: number};
export type DiagramEdge = {source: string; target: string; label: string};

export type Layer = {
  id: string;
  type: LayerKind;
  region: Region;
  text: string;
  shape: ShapeKind;
  chart: ChartKind;
  procedural: VisualKind | '';
  series: Series[];
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  steps: string[];
  points: number[];
  data_ref: string;
  unit: string;
  axis: string;
  source_note: string;
  color: Color;
  emphasis: number;
};

export type ResolvedAction = {
  target: string;
  kind: ActionKind;
  from: number;
  to: number;
  dx: number;
  dy: number;
  scale: number;
  degrees: number;
};

export type Caption = {start: number; end: number; text: string};
export type BeatTime = {at: number; fraction: number; purpose: string};

export type Scene = {
  id: string;
  heading: string;
  narration: string;
  visual: VisualKind;
  labels: string[];
  matrix: number[];
  color: Color;
  source_index: number;
  layout: LayoutKind;
  beats: {at: string; purpose: string}[];
  beat_times: BeatTime[];
  layers: Layer[];
  actions: {target: string; kind: ActionKind; start: string; end: string; dx: number; dy: number; scale: number; degrees: number}[];
  actions_resolved: ResolvedAction[];
  visual_intent: string;
  frames: number;
  captions: Caption[];
  caption_timing: string;
  layout_warnings: string[];
  duration: number;
};

export type MovieProps = {
  title: string;
  episode: string;
  fps: number;
  scenes: Scene[];
  sources: {label: string; url: string}[];
  layers: string[];
  cover: boolean;
  coverCaption: string;
  style: StyleName;
  schema_version: number;
};
