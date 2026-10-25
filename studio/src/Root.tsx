import React from 'react';
import {Composition} from 'remotion';
import {Movie} from './Movie';
import type {MovieProps} from './types';

const defaults: MovieProps = {
  title: '看见结构的力量', episode: 'Movelyth', fps: 30, cover: false,
  sources: [], layers: [],
  scenes: [{id: 'intro', heading: '让数学动起来', narration: '每一次变化，都有可以理解的结构。',
    visual: 'matrix', labels: ['观察变化'], matrix: [1, 0.6, 0, 1], color: 'cyan',
    source_index: 0, frames: 180, captions: []}],
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
