import React from 'react';
import {Composition} from 'remotion';
import {Movie} from './Movie';
import type {MovieProps} from './types';

const defaults: MovieProps = {
  title: '看见结构的力量', episode: 'Movelyth', fps: 30, cover: false, coverCaption: '', style: 'tech', schema_version: 1,
  sources: [], layers: [],
  scenes: [{
    id: 'intro', heading: '让数学动起来', narration: '每一次变化，都有可以理解的结构。',
    visual: 'matrix', labels: ['观察变化'], matrix: [1, 0.6, 0, 1], color: 'cyan', source_index: 0,
    layout: 'diagram', beats: [], beat_times: [], actions: [], actions_resolved: [],
    visual_intent: '示例：单位正方形被线性变换', frames: 180, captions: [], caption_timing: 'none',
    layout_warnings: [], duration: 6,
    layers: [{
      id: 'visual', type: 'procedural', region: 'main', text: '', shape: 'rect', chart: 'line',
      procedural: 'matrix', series: [], nodes: [], edges: [], steps: [], points: [], data_ref: '',
      unit: '', axis: '', source_note: '', color: 'cyan', emphasis: 1,
    }],
  }],
};

export const Root: React.FC = () => <>
  {(['Landscape', 'Portrait'] as const).map((id) => <Composition
    key={id} id={id} component={Movie} defaultProps={defaults}
    width={id === 'Landscape' ? 1920 : 1080} height={id === 'Landscape' ? 1080 : 1920}
    fps={30} durationInFrames={180}
    calculateMetadata={({props}) => ({
      durationInFrames: props.cover ? 90 : Math.max(1, props.scenes.reduce((n, s) => n + s.frames, 0)),
      fps: props.fps,
    })}
  />)}
</>;

