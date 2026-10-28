import type {CameraKeyframe, CameraKind, Layer, ResolvedAction} from './types';
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
        // A 16% ghost is useful for a chart that is about to draw, but a text
        // note at 16% looks disabled.  Text/formula layers stay hidden until
        // their action actually starts.
        if (action.from >= 0.15) ghost = Math.max(ghost, layer.type === 'text' || layer.type === 'math' ? 0 : 0.16);
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
export type CameraState = {scale: number; translateX: number; translateY: number};

/**
 * V3 camera: a slow move for the whole shot plus a re-frame at each coverage beat.
 *
 * V2 only moved 2–4% over a 25 s shot, so the picture was effectively frozen
 * after the entrance.  An editor covering the same 25 s would cut to a slightly
 * tighter framing when the argument moves on.  We cannot cut the layers (the
 * narration is continuous), but we can move the camera: 0.8 s after each beat
 * starts, the framing eases to a new target and then holds.  The move is bounded
 * (±3.5% scale, ±1.4% translate) so text stays inside its safe box.
 */
/**
 * Plan-driven camera: the Python side decides *what* to focus on (a real layer's
 * region box) and this function only interpolates between keyframes.  Captions and
 * the footer are drawn outside this transform, so they never zoom with the content.
 */
export const cameraFromPlan = (
  plan: CameraKeyframe[] | undefined,
  time: number,
): CameraState | null => {
  if (!plan || plan.length === 0) return null;
  const at = (key: CameraKeyframe): CameraState => ({
    scale: key.scale,
    translateX: (0.5 - key.cx) * key.scale,
    translateY: (0.5 - key.cy) * key.scale,
  });
  if (time <= plan[0].at) return at(plan[0]);
  for (let index = 1; index < plan.length; index++) {
    const previous = plan[index - 1];
    const next = plan[index];
    if (time < next.at) {
      // A keyframe holds its framing until the transition window that *ends* at the
      // next keyframe; easing from the previous keyframe instead would arrive early
      // and sit at the next framing for the whole shot.
      const window = Math.min(0.7, Math.max(0.001, next.at - previous.at));
      const k = ease(clamp((time - (next.at - window)) / window));
      const a = at(previous);
      const b = at(next);
      return {
        scale: a.scale + (b.scale - a.scale) * k,
        translateX: a.translateX + (b.translateX - a.translateX) * k,
        translateY: a.translateY + (b.translateY - a.translateY) * k,
      };
    }
  }
  return at(plan[plan.length - 1]);
};

export const cameraFor = (
  kind: CameraKind | undefined,
  progress: number,
  options: {beatIndex?: number; beatStartedAt?: number; seconds?: number; time?: number;
    plan?: CameraKeyframe[]} = {},
): CameraState => {
  const planned = cameraFromPlan(options.plan, options.time ?? progress * (options.seconds ?? 10));
  if (planned) return planned;
  const beatIndex = options.beatIndex ?? 0;
  const seconds = options.seconds ?? 10;
  const time = options.time ?? progress * seconds;
  // Settle 6% before the end: the last beat gets a stable hold instead of drifting
  // while the conclusion is being read.
  const settled = seconds > 4 ? Math.min(progress, 1 - 0.8 / seconds) : progress;
  const p = ease(clamp(settled));
  const base: CameraState = (() => {
    switch (kind) {
      case 'none':
        return {scale: 1, translateX: 0, translateY: 0};
      case 'pull':
        return {scale: 1.045 - 0.04 * p, translateX: 0, translateY: 0};
      case 'pan_left':
        return {scale: 1.035, translateX: 0.018 * (1 - p), translateY: 0};
      case 'pan_right':
        return {scale: 1.035, translateX: -0.018 * (1 - p), translateY: 0};
      case 'push':
      default:
        return {scale: 1 + 0.03 * p, translateX: 0, translateY: -0.01 * p};
    }
  })();
  // Beat targets: alternate between wide, tight and a slight left/right reframe.
  const targets = [1.0, 1.032, 1.014, 1.042];
  const beatTarget = kind === 'none' ? 1 : targets[beatIndex % targets.length];
  // Ease into the new framing over 0.8 s from the beat start, then hold still.
  const sinceBeat = Math.max(0, time - (options.beatStartedAt ?? 0));
  const k = ease(clamp(sinceBeat / 0.8));
  const previous = beatIndex === 0 ? 1 : targets[(beatIndex - 1) % targets.length];
  const scale = base.scale * (previous + (beatTarget - previous) * k);
  const side = beatIndex % 2 === 0 ? 1 : -1;
  const translateX = base.translateX + side * 0.011 * k * (beatIndex === 0 ? 0 : 1);
  const translateY = base.translateY - 0.005 * k * (beatIndex % 3 === 0 ? 0 : 1);
  return {scale, translateX, translateY};
};

/** A small heartbeat on the hero at each beat: visible, not a bouncing logo. */
export const beatPulse = (time: number, beatStartedAt: number): number => {
  const local = time - beatStartedAt;
  if (local < 0 || local > 1.2) return 0;
  return Math.sin(Math.PI * clamp(local / 1.2)) * 0.008;
};

export const percent = (value: number): string => `${(clamp(value) * 100).toFixed(2)}%`;
