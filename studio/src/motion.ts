import type {Layer, ResolvedAction} from './types';
import {clamp, ease} from './theme';

export type Motion = {
  opacity: number;
  reveal: number;
  translateX: number;
  translateY: number;
  scale: number;
  rotate: number;
  glow: number;
};

const progressOf = (action: ResolvedAction, progress: number): number => {
  const span = Math.max(0.001, action.to - action.from);
  return ease((progress - action.from) / span);
};

/**
 * Animation depends only on props and progress: no CSS keyframes, randomness or
 * realtime state.  Layers without explicit actions still get a deterministic
 * staggered entrance so a scene is never one static image for its whole length.
 */
export const motionFor = (
  layer: Layer,
  actions: ResolvedAction[],
  progress: number,
  index: number,
  motionScale: number,
): Motion => {
  const own = actions.filter((action) => action.target === layer.id);
  // Fast, staggered entrance: never leave a large blank frame at scene start.
  const stagger = 0.25 + 0.75 * ease(clamp((progress - index * 0.03) / Math.max(0.1, 0.22 * motionScale)));
  const result: Motion = {
    opacity: 1,
    reveal: clamp(stagger),
    translateX: 0,
    translateY: 0,
    scale: 1,
    rotate: 0,
    glow: 0,
  };
  let hasEntrance = false;
  for (const action of own) {
    const p = progressOf(action, progress);
    switch (action.kind) {
      case 'appear':
      case 'fade':
      case 'morph':
        result.opacity = Math.min(result.opacity, p);
        hasEntrance = true;
        break;
      case 'move':
        result.translateX += action.dx * (1 - p);
        result.translateY += action.dy * (1 - p);
        break;
      case 'scale':
        result.scale *= 1 + (action.scale - 1) * p;
        break;
      case 'rotate':
        result.rotate += action.degrees * p;
        break;
      case 'highlight':
        result.glow = Math.max(result.glow, p);
        break;
      case 'draw':
        result.reveal = Math.min(result.reveal, p);
        hasEntrance = true;
        break;
      default:
        break;
    }
  }
  if (hasEntrance) {
    result.opacity = Math.min(result.opacity, clamp(progress / 0.12 + 0.05));
  }
  return result;
};

export const percent = (value: number): string => `${(clamp(value) * 100).toFixed(2)}%`;

