import type {Color, StyleName, TransitionKind} from './types';

/**
 * V2 design tokens.
 *
 * The V1 theme only carried colours and one font size, so every screen ended up
 * with the same visual weight: a 58 px heading on a 1920 px canvas with 27 px
 * labels and no spacing system.  These tokens are the single place that decides
 * scale, rhythm and depth, and the components read them instead of inventing
 * numbers.  Type sizes follow Remotion's layout guidance (a 1080-wide
 * composition wants ~84 px for its main headline, so 1920 wants ~150 px for a
 * full-bleed title; our headings sit at 92–104 px because they share the frame
 * with a visual).
 */
export const accent: Record<Color, string> = {
  cyan: '#6fe6ef',
  amber: '#ffc978',
  coral: '#ff9285',
  mint: '#a3e8bd',
};

/** A second, cooler tone per accent so charts can use a gradient instead of one flat hue. */
export const accentDeep: Record<Color, string> = {
  cyan: '#2b9fbf',
  amber: '#d98f2c',
  coral: '#c9544a',
  mint: '#4f9f74',
};

export type TypeScale = {
  display: number;
  heading: number;
  subhead: number;
  body: number;
  caption: number;
  label: number;
  micro: number;
};

export type MotionProfile = {
  staggerSeconds: number;
  restLift: number;
  restScale: number;
  heroPulse: number;
  cameraMoveSeconds: number;
  overshoot: boolean;
  transitions: Record<TransitionKind, number>;
  /** Fraction of the scene camera movement followed by background/subject/reading layers. */
  planes: {background: number; subject: number; reading: number};
};

export type Theme = {
  name: StyleName;
  background: string;
  backgroundBase: string;
  overlay: string;
  surface: string;
  surfaceAlt: string;
  text: string;
  muted: string;
  faint: string;
  grid: string;
  fontFamily: string;
  fontFamilyDisplay: string;
  headingWeight: number;
  letterSpacing: number;
  motion: number;
  radius: number;
  type: TypeScale;
  /** Fraction of a second used by an entrance; scaled by `motion`. */
  enter: number;
  motionProfile: MotionProfile;
  shadow: string;
  /** Deep tone used for the insight card's border and the hero rim. */
  heroRim: string;
  /** Background mesh tint, layered under the vignette. */
  mesh: string;
};

const scale = (display: number, heading: number, body: number, caption: number): TypeScale => ({
  display,
  heading,
  subhead: Math.round(heading * 0.52),
  body,
  caption,
  label: Math.round(body * 0.82),
  micro: Math.round(body * 0.55),
});

export const themes: Record<StyleName, Theme> = {
  tech: {
    name: 'tech',
    background: 'linear-gradient(158deg, #0d2431 0%, #071520 58%, #05101a 100%)',
    backgroundBase: '#071520',
    overlay: 'radial-gradient(ellipse 70% 60% at 78% 18%, #1d465433, transparent 70%),'
      + 'radial-gradient(ellipse 60% 50% at 8% 92%, #12324340, transparent 72%)',
    surface: '#0b2230',
    surfaceAlt: '#12303f',
    text: '#f3f1e4',
    muted: '#93aab6',
    faint: '#5d7481',
    grid: '#8db1bc',
    fontFamily: '"Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans SC", sans-serif',
    fontFamilyDisplay: '"Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans SC", sans-serif',
    headingWeight: 700,
    letterSpacing: 0.5,
    motion: 1,
    radius: 18,
    type: scale(132, 112, 46, 66),
    enter: 0.52,
    motionProfile: {
      staggerSeconds: 0.045, restLift: 0.018, restScale: 0.008, heroPulse: 0.008,
      cameraMoveSeconds: 0.7, overshoot: true,
      transitions: {cut: 0, fade: 0.55, slide: 0.62, wipe: 0.58, dip: 0.66, zoom: 0.56},
      planes: {background: 0.72, subject: 1, reading: 0.28},
    },
    shadow: '0 26px 90px #00000066',
    heroRim: '#6fe6ef',
    mesh: 'radial-gradient(ellipse 60% 55% at 72% 32%, #1d5a6e42, transparent 68%),'
      + 'radial-gradient(ellipse 50% 45% at 18% 78%, #12324344, transparent 72%)',
  },
  minimal: {
    name: 'minimal',
    background: 'linear-gradient(162deg, #16160f 0%, #0d0d09 62%, #080806 100%)',
    backgroundBase: '#0d0d09',
    overlay: 'radial-gradient(ellipse 65% 55% at 22% 12%, #3d3d2b2e, transparent 68%),'
      + 'radial-gradient(ellipse 55% 45% at 88% 90%, #24241a3d, transparent 70%)',
    surface: '#1c1c15',
    surfaceAlt: '#26261c',
    text: '#f6f3e7',
    muted: '#a9a696',
    faint: '#6f6c5f',
    grid: '#c9c6b6',
    fontFamily: '"Microsoft YaHei", "Noto Sans CJK SC", "PingFang SC", sans-serif',
    fontFamilyDisplay: '"Microsoft YaHei", "Noto Sans CJK SC", "PingFang SC", sans-serif',
    headingWeight: 600,
    letterSpacing: 1.2,
    motion: 0.72,
    radius: 10,
    type: scale(124, 104, 44, 64),
    enter: 0.62,
    motionProfile: {
      staggerSeconds: 0.024, restLift: 0.008, restScale: 0.004, heroPulse: 0.003,
      cameraMoveSeconds: 0.55, overshoot: false,
      transitions: {cut: 0, fade: 0.38, slide: 0.45, wipe: 0.42, dip: 0.5, zoom: 0.42},
      planes: {background: 1, subject: 1, reading: 1},
    },
    shadow: '0 22px 70px #00000059',
    heroRim: '#e8d9a8',
    mesh: 'radial-gradient(ellipse 58% 50% at 70% 30%, #4a422b3a, transparent 70%),'
      + 'radial-gradient(ellipse 48% 42% at 16% 80%, #2b2b1d40, transparent 74%)',
  },
  documentary: {
    name: 'documentary',
    background: 'linear-gradient(152deg, #241a10 0%, #150f09 60%, #0d0906 100%)',
    backgroundBase: '#150f09',
    overlay: 'radial-gradient(ellipse 68% 58% at 74% 20%, #7a53302b, transparent 66%),'
      + 'radial-gradient(ellipse 55% 45% at 12% 88%, #3d2a1740, transparent 70%)',
    surface: '#2b2015',
    surfaceAlt: '#392a1b',
    text: '#f8eedc',
    muted: '#c3ac8e',
    faint: '#8b7458',
    grid: '#b99a72',
    fontFamily: '"Songti SC", "SimSun", "Microsoft YaHei", serif',
    fontFamilyDisplay: '"Songti SC", "SimSun", "Microsoft YaHei", serif',
    headingWeight: 700,
    letterSpacing: 1,
    motion: 0.86,
    radius: 6,
    type: scale(128, 108, 44, 64),
    enter: 0.58,
    motionProfile: {
      staggerSeconds: 0.032, restLift: 0.01, restScale: 0.005, heroPulse: 0.004,
      cameraMoveSeconds: 0.8, overshoot: false,
      transitions: {cut: 0, fade: 0.65, slide: 0.72, wipe: 0.68, dip: 0.78, zoom: 0.66},
      planes: {background: 0.45, subject: 1, reading: 0.16},
    },
    shadow: '0 24px 80px #0000005e',
    heroRim: '#ffc978',
    mesh: 'radial-gradient(ellipse 60% 52% at 72% 30%, #7a53302e, transparent 68%),'
      + 'radial-gradient(ellipse 50% 44% at 14% 82%, #3d2a1744, transparent 74%)',
  },
};

export const themeFor = (style: StyleName | string | undefined): Theme =>
  themes[(style as StyleName) in themes ? (style as StyleName) : 'tech'];

export const clamp = (value: number): number => Math.max(0, Math.min(1, value));

/** Smoothstep: a gentle in/out that never overshoots. */
export const ease = (value: number): number => {
  const p = clamp(value);
  return p * p * (3 - 2 * p);
};

/** Decelerating curve for entrances: fast start, soft settle. Matches cubic-bezier(.16,1,.3,1). */
export const easeOut = (value: number): number => {
  const p = clamp(value);
  return 1 - Math.pow(1 - p, 3);
};

/** Accelerating curve for exits, so a leaving element does not linger. */
export const easeIn = (value: number): number => {
  const p = clamp(value);
  return p * p * p;
};

/** A gentle overshoot used for "settle" moves. Deterministic, no spring state. */
export const springish = (value: number): number => {
  const p = clamp(value);
  if (p >= 1) return 1;
  const c = 1.32;
  return 1 - Math.exp(-6.2 * p) * Math.cos(c * 6.2 * p);
};

/** Fade in over [0, length] and out over the last [length] of a span. */
export const windowFade = (progress: number, length = 0.08): number =>
  Math.min(1, clamp(progress / length), clamp((1 - progress) / length));
