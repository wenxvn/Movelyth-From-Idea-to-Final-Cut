export type Color = 'cyan' | 'amber' | 'coral' | 'mint';
export type VisualKind = 'matrix' | 'vectors' | 'projection' | 'wave' | 'network' | 'image_layers' | 'orbit';
export type LayerKind = 'text' | 'shape' | 'math' | 'chart' | 'diagram' | 'timeline' | 'image' | 'procedural';
export type Region = 'main' | 'side' | 'top' | 'bottom' | 'annotation' | 'full';
export type LayoutKind = 'immersive' | 'diagram' | 'compare';
export type ActionKind = 'appear' | 'fade' | 'move' | 'scale' | 'rotate' | 'highlight' | 'draw' | 'morph';
export type ShapeKind = 'point' | 'line' | 'rect' | 'circle' | 'arrow' | 'polygon' | 'bracket';
export type ChartKind = 'line' | 'bar' | 'scatter';
export type StyleName = 'minimal' | 'tech' | 'documentary';
export type TransitionKind = 'cut' | 'fade' | 'slide' | 'wipe' | 'dip' | 'zoom';
export type CameraKind = 'none' | 'push' | 'pull' | 'pan_left' | 'pan_right';
export type CueKind = 'whoosh' | 'tick' | 'impact' | 'riser' | 'chime';
export type SceneRole = 'hook' | 'mechanism' | 'example' | 'turn' | 'conclusion';
export type EventKind = 'reveal' | 'transform' | 'compare' | 'conclude' | 'emphasis' | 'pause' | 'transition';

/** A named moment other stages bind to; resolved from real TTS boundaries. */
export type EventAnchor = {
  kind: 'start' | 'end' | 'fraction' | 'narration';
  fraction: number;
  text: string;
  occurrence: number;
  char_start: number | null;
  char_end: number | null;
};
export type SemanticEvent = {
  id: string;
  kind: EventKind;
  anchor: EventAnchor;
  offset_seconds: number;
  purpose: string;
  target: string;
};
export type CameraKeyframe = {
  at: number;
  mode: 'overview' | 'focus' | 'follow' | 'reframe';
  scale: number;
  cx: number;
  cy: number;
  target?: string;
  reason: string;
};
export type ResolvedEvent = {
  id: string;
  kind: EventKind;
  at: number;
  fraction: number;
  target: string;
  purpose: string;
  anchor: string;
  timing: string;
};

export type Annotation = {x: number; text: string};

export type Series = {label: string; values: number[]; unit: string; x_values: number[]};
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
  connect: boolean;
  annotations: Annotation[];
  highlight: number[];
  // v2 semantic identity: the subject survives across scenes, the layer id does not.
  subject_id?: string;
  state_before?: string;
  state_after?: string;
  visual_explanation?: string;
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

/** One real TTS word boundary inside a caption page, for karaoke highlighting. */
export type CaptionWord = {text: string; start: number; end: number};
export type Caption = {start: number; end: number; text: string; words?: CaptionWord[]};
export type BeatTime = {at: number; fraction: number; purpose: string};
export type SoundCue = {at: number; kind: CueKind; gain: number};

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
  transition?: TransitionKind;
  camera?: CameraKind;
  emphasis?: string[];
  cues_resolved?: SoundCue[];
  chapter?: string;
  role?: SceneRole;
  takeaway?: string;
  metric?: string;
  hero?: string;
  claim_ids?: string[];
  hold_reason?: string;
  transition_reason?: string;
  events?: SemanticEvent[];
  events_resolved?: ResolvedEvent[];
  camera_plan?: CameraKeyframe[];
  recipe?: string;
  schema_version?: number;
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
