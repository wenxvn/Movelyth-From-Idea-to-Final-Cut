export type Scene = {
  id: string;
  heading: string;
  narration: string;
  visual: 'matrix' | 'vectors' | 'projection' | 'wave' | 'network' | 'image_layers' | 'orbit';
  labels: string[];
  matrix: number[];
  color: 'cyan' | 'amber' | 'coral' | 'mint';
  source_index: number;
  frames: number;
  captions: {start: number; end: number; text: string}[];
};

export type MovieProps = {
  title: string;
  episode: string;
  fps: number;
  scenes: Scene[];
  sources: {label: string; url: string}[];
  layers: string[];
  cover: boolean;
};
