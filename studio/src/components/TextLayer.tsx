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

const fitSize = (text: string, box: Box, base: number, min: number, singleLine = false,
                 lineHeight = 1.34): number => {
  const lines = text.split('\n');
  const fits = (size: number): boolean => {
    if (singleLine && lines.length === 1) {
      const width = Array.from(lines[0]).reduce((total, ch) => total + charEm(ch) * size, 0);
      return width <= box.w && size * lineHeight <= box.h;
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
    return rows * size * lineHeight <= box.h;
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
    const base = Math.round((theme.type.subhead + emphasis * 16) * regionFactor * (vertical ? 1.06 : 1));
    // The card has internal padding; fitting against the raw region made a long
    // one-line formula wrap at the last token and clip its second line.
    const inner = {x: box.x, y: box.y, w: Math.max(80, box.w - Math.round(base * 0.62)),
      h: Math.max(40, box.h - Math.round(base * 0.42))};
    const size = fitSize(layer.text, inner, base, 38, true);
    const singleLine = !layer.text.includes('\n');
    const parts = layer.text.split(/([=＝])/);
    const equalAt = parts.findIndex((part) => part === '=' || part === '＝');
    return <div style={{width: '100%', height: '100%', display: 'flex', alignItems: 'center',
      justifyContent: 'center', opacity: reveal}}>
      <div style={{
        fontSize: size, lineHeight: 1.34, fontWeight: 600, color,
        fontFamily: '"Cascadia Mono", "Consolas", "Cambria Math", monospace',
        letterSpacing: 0.4, whiteSpace: singleLine ? 'nowrap' : 'pre-wrap',
        width: '100%', minWidth: 0, maxWidth: '100%', maxHeight: '100%', boxSizing: 'border-box',
        overflow: 'hidden', textAlign: 'center',
        padding: `${Math.round(size * 0.22)}px ${Math.round(size * 0.3)}px`,
        background: `linear-gradient(150deg, ${theme.surfaceAlt}f2, ${theme.surface}e0)`,
        borderLeft: `5px solid ${deep}`, borderRadius: theme.radius * 0.7, boxShadow: theme.shadow,
        position: 'relative',
      }}>
        <div style={{position: 'absolute', right: 14, top: 8, fontSize: Math.max(18, Math.round(size * 0.3)),
          letterSpacing: 3, color: `${color}99`, fontWeight: 700}}>FORMULA</div>
        {equalAt >= 0 ? <>
          <span>{parts.slice(0, equalAt).join('')}</span>
          <span style={{color: deep}}>=</span>
          <span style={{color}}>{parts.slice(equalAt + 1).join('')}</span>
        </> : withBreaks(layer.text)}
      </div>
    </div>;
  }

  const kicker = layer.region === 'top';
  const base = Math.round((theme.type.body + emphasis * 8) * regionFactor * (vertical ? 1.08 : 1));
  const size = fitSize(layer.text, box, base, 28);

  // Narrow annotation strips cannot accommodate the normal card's padding.
  // Render an unpadded line within the strip instead of clipping its lower half.
  if (!kicker && box.h < 60) {
    const stripSize = fitSize(layer.text, box, Math.min(24, Math.floor(box.h / 1.2)), 14, false, 1.1);
    return <div style={{width: '100%', height: '100%', display: 'flex', alignItems: 'center',
      opacity: reveal, color: theme.text, fontFamily: theme.fontFamily, fontSize: stripSize,
      lineHeight: 1.1, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{withBreaks(layer.text)}</div>;
  }

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
      fontSize: size, lineHeight: 1.36, fontWeight: 650, color: theme.text,
      fontFamily: theme.fontFamily, letterSpacing: theme.letterSpacing * 0.3,
      overflowWrap: 'anywhere', wordBreak: 'break-word', whiteSpace: 'pre-wrap',
      maxWidth: '100%', maxHeight: '100%', overflow: 'hidden', textAlign: 'left',
      borderLeft: `${Math.max(4, Math.round(size * 0.12))}px solid ${color}`,
      background: `linear-gradient(120deg, ${theme.surface}cc, ${theme.surface}66)`,
      borderRadius: 12,
      padding: `${Math.round(size * 0.26)}px ${Math.round(size * 0.5)}px`,
      paddingLeft: Math.round(size * 0.62),
    }}>{withBreaks(layer.text)}</div>
  </div>;
};
