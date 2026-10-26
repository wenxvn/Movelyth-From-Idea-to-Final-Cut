import React from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';
import type {Layer, Scene} from './types';
import type {Theme} from './theme';
import {accent} from './theme';
import {regions} from './layouts';
import {motionFor} from './motion';
import {TextLayer} from './components/TextLayer';
import {ShapeLayer} from './components/ShapeLayer';
import {ChartLayer} from './components/ChartLayer';
import {DiagramLayer} from './components/DiagramLayer';
import {TimelineLayer} from './components/TimelineLayer';
import {ImageLayer} from './components/ImageLayer';
import {ProceduralLayer} from './components/ProceduralLayer';

export type Box = {x: number; y: number; w: number; h: number};

type RenderProps = {
  layer: Layer;
  scene: Scene;
  theme: Theme;
  vertical: boolean;
  time: number;
  progress: number;
  reveal: number;
  layers: string[];
  box: Box;
};

const renderers: Record<Layer['type'], (props: RenderProps) => React.ReactNode> = {
  text: ({layer, theme, vertical, reveal, box}) =>
    <TextLayer layer={layer} theme={theme} vertical={vertical} reveal={reveal} box={box} math={false}/>,
  math: ({layer, theme, vertical, reveal, box}) =>
    <TextLayer layer={layer} theme={theme} vertical={vertical} reveal={reveal} box={box} math/>,
  shape: ({layer, theme, reveal}) => <ShapeLayer layer={layer} theme={theme} reveal={reveal}/>,
  chart: ({layer, theme, vertical, reveal}) => <ChartLayer layer={layer} theme={theme} vertical={vertical} reveal={reveal}/>,
  diagram: ({layer, theme, time, reveal, box}) =>
    <DiagramLayer layer={layer} theme={theme} time={time} reveal={reveal} box={box}/>,
  timeline: ({layer, theme, vertical, reveal}) => <TimelineLayer layer={layer} theme={theme} reveal={reveal} vertical={vertical}/>,
  image: ({layer, theme, layers, reveal}) => <ImageLayer layer={layer} theme={theme} layers={layers} reveal={reveal}/>,
  procedural: ({layer, scene, time, progress, reveal, layers}) =>
    <ProceduralLayer layer={layer} scene={scene} time={time} progress={progress} reveal={reveal} layers={layers}/>,
};

export const SceneStage: React.FC<{
  scene: Scene; layout?: string; time: number; progress: number; layers: string[]; vertical: boolean; theme: Theme;
}> = ({scene, layout, time, progress, layers, vertical, theme}) => {
  const {width, height} = useVideoConfig();
  const boxes = regions(vertical, layout || scene.layout);
  return <AbsoluteFill>
    {scene.layers.map((layer, index) => {
      const motion = motionFor(layer, scene.actions_resolved || [], progress, index, theme.motion);
      const box: Box = layer.region === 'full'
        ? {x: 0, y: 0, w: width, h: height}
        : (boxes[layer.region] || boxes.main);
      const render = renderers[layer.type];
      const color = accent[layer.color] || theme.text;
      return <div key={layer.id} style={{
        position: 'absolute', left: box.x, top: box.y, width: box.w, height: box.h,
        opacity: motion.opacity,
        transform: `translate(${motion.translateX * box.w}px, ${motion.translateY * box.h}px) scale(${motion.scale}) rotate(${motion.rotate}deg)`,
        transformOrigin: 'center center',
        filter: motion.glow > 0.01 ? `drop-shadow(0 0 ${18 * motion.glow}px ${color})` : undefined,
        display: 'flex', alignItems: 'stretch', justifyContent: 'stretch',
      }}>
        {render ? render({layer, scene, theme, vertical, time, progress,
                          reveal: motion.reveal, layers, box}) : null}
      </div>;
    })}
  </AbsoluteFill>;
};
