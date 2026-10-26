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

/** Largest size (down to the minimum) whose wrapped text still fits the box. */
const fitSize = (text: string, box: Box, base: number, min: number): number => {
  const lines = text.split('\n');
  let size = base;
  while (size > min) {
    const perLine = Math.max(1, Math.floor(box.w / (size * 1.02)));
    const needed = lines.reduce((total, line) => total + Math.max(1, Math.ceil(line.length / perLine)), 0);
    if (needed * size * 1.42 <= box.h) return size;
    size -= 2;
  }
  return min;
};

export const TextLayer: React.FC<{
  layer: Layer; theme: Theme; vertical: boolean; reveal: number; math: boolean; box: Box;
}> = ({layer, theme, vertical, reveal, math, box}) => {
  const emphasis = Math.max(0, Math.min(2, layer.emphasis - 1));
  const base = BASE[math ? 'math' : 'text'][emphasis];
  const size = fitSize(layer.text, box, Math.round(base * (vertical ? 1.1 : 1)), MIN[math ? 'math' : 'text']);
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
