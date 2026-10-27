import React from 'react';
import type {Layer} from '../types';
import type {Theme} from '../theme';
import {accent} from '../theme';
import type {Box} from '../Stage';

/** Keep explicit line breaks so matrix rows written by the director stay rows. */
const withBreaks = (text: string): React.ReactNode[] =>
  text.split('\n').flatMap((line, index) => (index === 0 ? [line] : [<br key={`br${index}`}/>, line]));

const BASE = {text: [30, 36, 44], math: [56, 68, 86]};
const MIN = {text: 22, math: 34};

/**
 * Largest size (down to the minimum) whose wrapped text still fits the box.
 *
 * `singleLine` is for formulas: a math layer is one expression, so it shrinks
 * until it fits on one line instead of wrapping at "=" and leaving a fragment.
 * Explicit \n still produces the rows the director asked for (matrix rows).
 */
const fitSize = (text: string, box: Box, base: number, min: number, singleLine = false): number => {
  const lines = text.split('\n');
  const CHAR = 1.02; // One full-width CJK glyph per em; conservative for mixed text.
  const LINE = 1.42;
  const fits = (size: number): boolean => {
    if (singleLine && lines.length === 1) {
      // One expression on one line: it must fit the width AND the box height, or the
      // line is clipped instead of wrapped (a real render lost half a formula this way).
      return lines[0].length * size * CHAR <= box.w && size * LINE <= box.h;
    }
    const perLine = Math.max(1, Math.floor(box.w / (size * CHAR)));
    const rows = lines.reduce((total, line) => total + Math.max(1, Math.ceil(line.length / perLine)), 0);
    return rows * size * LINE <= box.h;
  };
  let size = base;
  while (size > min) {
    if (fits(size)) return size;
    size -= 2;
  }
  return min;
};

export const TextLayer: React.FC<{
  layer: Layer; theme: Theme; vertical: boolean; reveal: number; math: boolean; box: Box;
}> = ({layer, theme, vertical, reveal, math, box}) => {
  const emphasis = Math.max(0, Math.min(2, layer.emphasis - 1));
  const base = BASE[math ? 'math' : 'text'][emphasis];
  const size = fitSize(layer.text, box, Math.round(base * (vertical ? 1.1 : 1)), MIN[math ? 'math' : 'text'], math);
  const color = layer.color ? accent[layer.color] : theme.text;
  return (
    <div style={{
      width: '100%', height: '100%', display: 'flex',
      alignItems: math ? 'center' : 'flex-start',
      justifyContent: math ? 'center' : 'flex-start',
      opacity: reveal,
    }}>
      <div style={{
        fontSize: size,
        lineHeight: math ? 1.42 : 1.42,
        fontWeight: 600,
        color: math ? color : theme.text,
        fontFamily: math ? '"Cascadia Mono", "Consolas", "Cambria Math", monospace' : theme.fontFamily,
        letterSpacing: math ? 0.5 : theme.letterSpacing * 0.4,
        overflowWrap: 'anywhere',
        wordBreak: 'break-word',
        whiteSpace: 'pre-wrap',
        maxWidth: '100%',
        maxHeight: '100%',
        overflow: 'hidden',
        textAlign: math ? 'center' : 'left',
        background: math ? `${theme.surface}e6` : 'transparent',
        borderLeft: math ? 'none' : `5px solid ${color}`,
        borderRadius: math ? theme.radius : 0,
        padding: math ? '14px 20px' : '0 0 0 18px',
        boxShadow: math ? '0 12px 40px #0006' : 'none',
      }}>
        {withBreaks(layer.text)}
      </div>
    </div>
  );
};
