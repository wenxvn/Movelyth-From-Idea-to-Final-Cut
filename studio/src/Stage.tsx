import React from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';
import type {Layer, Scene} from './types';
import type {Theme} from './theme';
import {accent, accentDeep} from './theme';
import {isFullBleed, regions} from './layouts';
import {beatPulse, cameraFor, motionFor} from './motion';
import type {Beat} from './insights';
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
  beat: number;
  beats: Beat[];
  showAnnotations: boolean;
};

const renderers: Record<Layer['type'], (props: RenderProps) => React.ReactNode> = {
  text: ({layer, theme, vertical, reveal, box}) =>
    <TextLayer layer={layer} theme={theme} vertical={vertical} reveal={reveal} box={box} math={false}/>,
  math: ({layer, theme, vertical, reveal, box}) =>
    <TextLayer layer={layer} theme={theme} vertical={vertical} reveal={reveal} box={box} math/>,
  shape: ({layer, theme, reveal}) => <ShapeLayer layer={layer} theme={theme} reveal={reveal}/>,
  chart: ({layer, theme, vertical, reveal, box, beat, beats, scene, showAnnotations}) =>
    <ChartLayer layer={layer} theme={theme} vertical={vertical} reveal={reveal} box={box}
      beat={beat} beats={beats} scene={scene} showAnnotations={showAnnotations}/>,
  diagram: ({layer, theme, time, reveal, box}) =>
    <DiagramLayer layer={layer} theme={theme} time={time} reveal={reveal} box={box}/>,
  timeline: ({layer, theme, vertical, reveal}) => <TimelineLayer layer={layer} theme={theme} reveal={reveal} vertical={vertical}/>,
  image: ({layer, theme, layers, reveal}) => <ImageLayer layer={layer} theme={theme} layers={layers} reveal={reveal}/>,
  procedural: ({layer, scene, time, progress, reveal, layers, box}) =>
    <ProceduralLayer layer={layer} scene={scene} time={time} progress={progress} reveal={reveal}
      layers={layers} box={box}/>,
};

export const SceneStage: React.FC<{
  scene: Scene; layout?: string; time: number; progress: number; layers: string[]; vertical: boolean; theme: Theme;
  beat?: number; beats?: Beat[]; heroId?: string; showAnnotations?: boolean;
}> = ({scene, layout, time, progress, layers, vertical, theme, beat = 0, beats = [], heroId = '', showAnnotations = true}) => {
  const {width, height} = useVideoConfig();
  const activeLayout = layout || scene.layout;
  const boxes = regions(vertical, activeLayout);
  // On the full-width layout the three short-note slots sit on one row under the
  // headline.  If a script only uses one of them, that note belongs on the left
  // (aligned with the title), not floating in the middle of the frame.
  if (activeLayout === 'immersive') {
    const order = ['top', 'side', 'annotation'] as const;
    const slots = order.map((region) => boxes[region]).filter(Boolean);
    order.filter((region) => scene.layers.some((layer) => layer.region === region))
      .forEach((region, index) => {
        if (slots[index]) boxes[region] = slots[index];
      });
  }
  // Reclaim unused space above the main visual.  A portrait frame reserves bands for
  // an optional kicker and formula; when those layers are absent the visual was left
  // floating below a 300 px hole.  This only moves the top edge up to the lowest
  // *used* band, so it can never cover another layer.
  if (boxes.main && !isFullBleed(activeLayout, 'main')) {
    const backgrounds = new Set(['full']);
    let ceiling = Math.max(boxes.main.y, 0);
    let lowest = 0;
    for (const layer of scene.layers) {
      if (backgrounds.has(layer.region) || layer.region === 'main') continue;
      const box = boxes[layer.region];
      if (!box) continue;
      if (box.y + box.h <= ceiling) lowest = Math.max(lowest, box.y + box.h);
    }
    const gap = 24;
    if (lowest > 0 && ceiling - lowest > gap * 2) {
      const shift = ceiling - lowest - gap;
      boxes.main = {...boxes.main, y: boxes.main.y - shift, h: boxes.main.h + shift};
    }
  }
  // A slow camera move keeps a 25 s shot alive; it is bounded to a few percent so
  // it reads as "filmed" rather than as a zoom effect.
  const activeHero = heroId || scene.hero || '';
  const camera = cameraFor(scene.camera, progress, {
    beatIndex: beat, beatStartedAt: beats[beat]?.start ?? 0,
    seconds: scene.duration || scene.frames / 30, time,
    // The plan is computed from real layer regions in Python; when it exists it wins
    // over the decorative per-beat push, because it points at the subject.
    plan: scene.camera_plan,
  });
  const pulse = beatPulse(time, beats[beat]?.start ?? 0);
  return <AbsoluteFill>
    <AbsoluteFill style={{
      transform: `scale(${camera.scale}) translate(${camera.translateX * 100}%, ${camera.translateY * 100}%)`,
      transformOrigin: 'center center',
    }}>
      {scene.layers.map((layer, index) => {
        const motion = motionFor(layer, scene.actions_resolved || [], progress, index, theme.motion);
        const isHero = activeHero ? layer.id === activeHero : false;
        // Compare layouts have two competing pictures; the beat decides which one
        // is the subject, and the other one steps back without disappearing.
        const unfocused = Boolean(activeHero) && !isHero && layer.region === 'side' && layout === 'compare';
        const heroScale = isHero ? 1 + pulse : 1;
        const heroOpacity = unfocused ? 0.72 : 1;
        const box: Box = isFullBleed(activeLayout, layer.region)
          ? {x: 0, y: 0, w: width, h: height}
          : (boxes[layer.region] || boxes.main);
        const render = renderers[layer.type];
        const color = accent[layer.color] || theme.text;
        const deep = accentDeep[layer.color] || color;
        return <div key={layer.id} style={{
          position: 'absolute', left: box.x, top: box.y, width: box.w, height: box.h,
          opacity: motion.opacity * heroOpacity,
          transform: `translate(${motion.translateX * box.w}px, ${motion.translateY * box.h}px)`
            + ` scale(${motion.scale * heroScale}) rotate(${motion.rotate}deg)`,
          transformOrigin: 'center center',
          filter: isHero
            ? `drop-shadow(0 0 ${18 + 10 * pulse * 100}px ${color}55)`
            : motion.glow > 0.01
              ? `drop-shadow(0 0 ${14 + 22 * motion.glow}px ${color}aa)`
              : undefined,
          display: 'flex', alignItems: 'stretch', justifyContent: 'stretch',
        }}>
          {render ? render({layer, scene, theme, vertical, time, progress,
                            reveal: motion.reveal, layers, box, beat, beats, showAnnotations}) : null}
          {/* A hairline accent on highlighted *visual* layers, drawn outside the SVG
              so it reads as a selection in the composition.  A text layer gets the
              glow only: a box around a sentence looks like a form field. */}
          {(motion.glow > 0.02 || isHero) && layer.region === 'main' && <div style={{
            position: 'absolute', inset: -10, borderRadius: theme.radius + 6,
            border: `2px solid ${deep}`, opacity: 0.16 + 0.24 * motion.glow, pointerEvents: 'none',
          }}/>}
        </div>;
      })}
    </AbsoluteFill>
  </AbsoluteFill>;
};
