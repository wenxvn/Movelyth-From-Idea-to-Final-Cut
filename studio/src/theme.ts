import type {Color, StyleName} from './types';

export const accent: Record<Color, string> = {
  cyan: '#68e5ed', amber: '#ffc976', coral: '#ff8e80', mint: '#9de2b6',
};

export type Theme = {
  name: StyleName;
  background: string;
  overlay: string;
  surface: string;
  text: string;
  muted: string;
  grid: string;
  fontFamily: string;
  headingWeight: number;
  letterSpacing: number;
  motion: number;
  radius: number;
};

export const themes: Record<StyleName, Theme> = {
  tech: {
    name: 'tech',
    background: 'linear-gradient(145deg, #0f2736, #07151f 60%)',
    overlay: 'radial-gradient(ellipse at 80% 35%, #1e394433, transparent 65%)',
    surface: '#0b2230',
    text: '#f0eedf',
    muted: '#86a0ac',
    grid: '#8db1bc',
    fontFamily: '"Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans SC", sans-serif',
    headingWeight: 700,
    letterSpacing: 1,
    motion: 1,
    radius: 18,
  },
  minimal: {
    name: 'minimal',
    background: 'linear-gradient(160deg, #14140f, #0c0c0a 70%)',
    overlay: 'radial-gradient(ellipse at 20% 15%, #3a3a2a33, transparent 60%)',
    surface: '#1b1b16',
    text: '#f4f1e6',
    muted: '#a5a293',
    grid: '#c9c6b6',
    fontFamily: '"Microsoft YaHei", "Noto Sans CJK SC", "PingFang SC", sans-serif',
    headingWeight: 600,
    letterSpacing: 2,
    motion: 0.7,
    radius: 8,
  },
  documentary: {
    name: 'documentary',
    background: 'linear-gradient(150deg, #20180f, #120d09 65%)',
    overlay: 'radial-gradient(ellipse at 75% 25%, #6b4a2a2e, transparent 62%)',
    surface: '#2a1f15',
    text: '#f6ecdc',
    muted: '#c0a98c',
    grid: '#b99a72',
    fontFamily: '"Songti SC", "SimSun", "Microsoft YaHei", serif',
    headingWeight: 700,
    letterSpacing: 1.5,
    motion: 0.85,
    radius: 6,
  },
};

export const themeFor = (style: StyleName | string | undefined): Theme =>
  themes[(style as StyleName) in themes ? (style as StyleName) : 'tech'];

export const clamp = (value: number): number => Math.max(0, Math.min(1, value));
export const ease = (value: number): number => {
  const p = clamp(value);
  return p * p * (3 - 2 * p);
};
