import React from 'react';
import type {Layer} from '../types';
import type {Theme} from '../theme';
import {accent, accentDeep} from '../theme';
import type {Box} from '../Stage';

/** Keep explicit line breaks so matrix rows written by the director stay rows. */
const withBreaks = (text: string): React.ReactNode[] =>
  text.split('\n').flatMap((line, index) => (index === 0 ? [line] : [<br key={`br${index}`}/>, line]));

/**
 * Largest size (down to the minimum) whose wrapped text still fits the box.
 *
 * `singleLine` is for formulas: a math layer is one expression, so it shrinks
 * until it fits on one line instead of wrapping at "=" and leaving a fragment.
 * Widths are estimated in em (CJK 1em, Latin ~0.56em) instead of counting every
 * character as full-width, which used to shrink mixed text to half size.
 */
const charEm = (ch: string): number => {
  const code = ch.codePointAt(0) ?? 0;
  if (code < 0x2000) return 0.56;
  if (code >= 0xff00) return 1;
  if (code >= 0x3000) return 1;
  return 0.62;
};

const fitSize = (text: string, box: Box, base: number, min: number, singleLine = false): number => {
  const lines = text.split('\n');
  const LINE = 1.34;
  const fits = (size: number): boolean => {
    if (singleLine && lines.length === 1) {
      const width = Array.from(lines[0]).reduce((total, ch) => total + charEm(ch) * size, 0);
      return width <= box.w && size * LINE <= box.h;
    }
    let rows = 0;
    for (const line of lines) {
      let used = 0;
      let count = 1;
      for (const ch of line) {
        const width = charEm(ch) * size;
        if (used + width > box.w && used > 0) {
          count += 1;
          used = width;
        } else {
          used += width;
        }
      }
      rows += count;
    }
    return rows * size * LINE <= box.h;
  };
  let size = base;
  while (size > min) {
    if (fits(size)) return size;
    size -= 2;
  }
  return min;
};

const REGION_BASE: Record<string, number> = {main: 1, bottom: 0.92, top: 0.82, side: 0.86, annotation: 0.86};

export const TextLayer: React.FC<{
  layer: Layer; theme: Theme; vertical: boolean; reveal: number; math: boolean; box: Box;
}> = ({layer, theme, vertical, reveal, math, box}) => {
  const emphasis = Math.max(0, Math.min(2, layer.emphasis - 1));
  const regionFactor = REGION_BASE[layer.region] ?? 0.9;
  const color = accent[layer.color] || theme.text;
  const deep = accentDeep[layer.color] || color;

  if (math) {
    const base = Math.round((theme.type.subhead + emphasis * 14) * regionFactor * (vertical ? 1.06 : 1));
    const size = fitSize(layer.text, box, base, 30, true);
    return <div style={{width: '100%', height: '100%', display: 'flex', alignItems: 'center',
      justifyContent: 'center', opacity: reveal}}>
      <div style={{
        fontSize: size, lineHeight: 1.34, fontWeight: 600, color,
        fontFamily: '"Cascadia Mono", "Consolas", "Cambria Math", monospace',
        letterSpacing: 0.4, whiteSpace: 'pre-wrap', maxWidth: '100%', maxHeight: '100%',
        overflow: 'hidden', textAlign: 'center', padding: `${Math.round(size * 0.34)}px ${Math.round(size * 0.5)}px`,
        background: `linear-gradient(150deg, ${theme.surfaceAlt}f2, ${theme.surface}e0)`,
        borderLeft: `4px solid ${deep}`, borderRadius: theme.radius * 0.7, boxShadow: theme.shadow,
      }}>{withBreaks(layer.text)}</div>
    </div>;
  }

  const kicker = layer.region === 'top';
  const base = Math.round((theme.type.body + emphasis * 6) * regionFactor * (vertical ? 1.08 : 1));
  const size = fitSize(layer.text, box, base, 24);

  if (kicker) {
    // A kicker is a label above the visual, not a second paragraph: small, spaced,
    // accent-coloured, no box, so it does not compete with the heading.
    return <div style={{width: '100%', height: '100%', display: 'flex', alignItems: 'center',
      justifyContent: 'flex-start', opacity: reveal}}>
      <div style={{display: 'flex', alignItems: 'center', gap: Math.round(size * 0.5)}}>
        <span style={{width: Math.round(size * 0.55), height: 3, background: color, borderRadius: 2,
          display: 'inline-block'}}/>
        <span style={{fontSize: Math.round(size * 0.82), letterSpacing: Math.max(1, size * 0.09),
          color, fontWeight: 700, textTransform: 'none', whiteSpace: 'pre-wrap'}}>{layer.text}</span>
      </div>
    </div>;
  }

  return <div style={{width: '100%', height: '100%', display: 'flex', alignItems: 'flex-start',
    justifyContent: 'flex-start', opacity: reveal}}>
    <div style={{
      fontSize: size, lineHeight: 1.34, fontWeight: 600, color: theme.text,
      fontFamily: theme.fontFamily, letterSpacing: theme.letterSpacing * 0.3,
      overflowWrap: 'anywhere', wordBreak: 'break-word', whiteSpace: 'pre-wrap',
      maxWidth: '100%', maxHeight: '100%', overflow: 'hidden', textAlign: 'left',
      borderLeft: `${Math.max(3, Math.round(size * 0.11))}px solid ${color}`,
      paddingLeft: Math.round(size * 0.55),
      paddingTop: Math.round(size * 0.12),
      paddingBottom: Math.round(size * 0.12),
    }}>{withBreaks(layer.text)}</div>
  </div>;
};
