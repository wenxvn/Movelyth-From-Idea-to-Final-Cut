import type {CameraKind, Layer, ResolvedAction} from './types';
import {clamp, ease, easeOut, springish} from './theme';

export type Motion = {
  opacity: number;
  /** How much of the drawing is revealed (used by draw actions). */
  reveal: number;
  translateX: number;
  translateY: number;
  scale: number;
  rotate: number;
  glow: number;
};

const progressOf = (action: ResolvedAction, progress: number): number =>
  easeOut((progress - action.from) / Math.max(0.001, action.to - action.from));

/**
 * Per-layer animation.  Depends only on props and progress: no CSS keyframes,
 * randomness, timers or realtime state, so every frame is reproducible.
 *
 * V1 applied one global "fade + 14 px up" to every layer, and a `draw` action
 * also raised opacity from 0.05, which let a half-built scene show through before
 * its animation started.  Here `reveal` and `opacity` are separate: a drawing
 * action only controls how much of the path is drawn, while the layer is fully
 * present.
 */
export const motionFor = (
  layer: Layer,
  actions: ResolvedAction[],
  progress: number,
  index: number,
  motionScale: number,
): Motion => {
  const own = actions.filter((action) => action.target === layer.id);
  // Semantic order: the hero visual arrives first, notes settle after it.
  const delay = index * 0.045 * motionScale;
  const settle = springish(clamp((progress - delay) / (0.34 * motionScale)));
  const result: Motion = {
    opacity: 1,
    reveal: 1,
    translateX: 0,
    translateY: 0,
    scale: 1,
    rotate: 0,
    glow: 0,
  };
  let hasEntrance = false;
  let hasDraw = false;
  // A layer whose entrance is anchored late in the sentence (which is correct for
  // "the conclusion appears when it is said") leaves the frame nearly empty for the
  // first second.  Keeping a faint ghost of it — the way an editor pre-places
  // elements and dims them — gives the eye something to look at without claiming the
  // point has already been made.
  let ghost = 0;
  for (const action of own) {
    const p = progressOf(action, progress);
    switch (action.kind) {
      case 'appear':
      case 'fade':
      case 'morph':
        if (action.from >= 0.15) ghost = Math.max(ghost, 0.16);
        result.opacity = Math.min(result.opacity, ghost + (1 - ghost) * p);
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
      case 'highlight': {
        // A slow breathing glow reads as "look here" without strobing.
        const breathe = 0.78 + 0.22 * Math.sin(progress * 26 + index);
        result.glow = Math.max(result.glow, p * breathe);
        break;
      }
      case 'draw': {
        // A `draw` that starts at 40% of a 25 s shot left the chart empty for ten
        // seconds.  Structured drawings (bars, dots, nodes) are pre-revealed so the
        // frame is never blank, while a line still reads as being drawn.
        const floor = layer.type === 'chart' && layer.chart === 'line' ? 0.06
          : layer.type === 'procedural' ? 0.0 : 0.45;
        result.reveal = Math.min(result.reveal, floor + (1 - floor) * p);
        hasDraw = true;
        break;
      }
      default:
        break;
    }
  }
  if (!hasEntrance && !hasDraw) {
    // Default entrance: a short, decelerating settle with a tiny rise.  The
    // displacement is small on purpose — big slides are what made V1 look like a
    // slide deck rather than a film.
    result.opacity = clamp(settle);
    result.translateY = 0.018 * (1 - settle);
    result.scale = 0.992 + 0.008 * settle;
  } else if (hasDraw) {
    // Keep the layer present; the draw progress controls the stroke itself.
    result.opacity = 1;
  }
  return result;
};

/** Camera transform for the whole scene, so a long shot never sits perfectly still. */
export const cameraFor = (kind: CameraKind | undefined, progress: number): {
  scale: number; translateX: number; translateY: number;
} => {
  const p = ease(clamp(progress));
  switch (kind) {
    case 'none':
      return {scale: 1, translateX: 0, translateY: 0};
    case 'pull':
      return {scale: 1.035 - 0.035 * p, translateX: 0, translateY: 0};
    case 'pan_left':
      return {scale: 1.04, translateX: 0.018 * (1 - p), translateY: 0};
    case 'pan_right':
      return {scale: 1.04, translateX: -0.018 * (1 - p), translateY: 0};
    case 'push':
    default:
      return {scale: 1 + 0.022 * p, translateX: 0, translateY: -0.008 * p};
  }
};

export const percent = (value: number): string => `${(clamp(value) * 100).toFixed(2)}%`;
