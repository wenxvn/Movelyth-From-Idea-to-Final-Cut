import React from 'react';
import type {Layer} from '../types';
import type {Theme} from '../theme';
import {accent} from '../theme';

const tokenize = (text: string): React.ReactNode[] => {
  const nodes: React.ReactNode[] = [];
  let buffer = '';
  let index = 0;
  const flush = () => {
    if (buffer) {
      nodes.push(<React.Fragment key={`t${index++}`}>{buffer.replace(/\*/g, '·')}</React.Fragment>);
      buffer = '';
    }
  };
  while (index < text.length) {
    const char = text[index];
    if ((char === '^' || char === '_') && index + 1 < text.length) {
      flush();
      let value = '';
      let cursor = index + 1;
      if (text[cursor] === '{') {
        const close = text.indexOf('}', cursor);
        value = close > cursor ? text.slice(cursor + 1, close) : text.slice(cursor + 1);
        index = close > cursor ? close + 1 : text.length;
      } else {
        value = text[cursor];
        index = cursor + 1;
      }
      nodes.push(char === '^' ? <sup key={`s${index}`}>{value}</sup> : <sub key={`s${index}`}>{value}</sub>);
      continue;
    }
    buffer += char;
    index += 1;
  }
  flush();
  return nodes;
};

export const TextLayer: React.FC<{layer: Layer; theme: Theme; vertical: boolean; reveal: number; math: boolean}> =
({layer, theme, vertical, reveal, math}) => {
  const base = [30, 36, 44][Math.max(0, Math.min(2, layer.emphasis - 1))];
  const size = Math.round(base * (vertical ? 1.18 : 1));
  const color = layer.color ? accent[layer.color] : theme.text;
  // Fit long strings into the box instead of overflowing into the captions.
  const perLine = Math.max(1, Math.floor(100 / (size * 1.02)));
  const fit = layer.text.length > perLine ? Math.max(18, Math.round(size * perLine / layer.text.length * 1.6)) : size;
  return (
    <div style={{
      width: '100%', height: '100%', display: 'flex',
      alignItems: math ? 'center' : 'flex-start',
      justifyContent: math ? 'center' : 'flex-start',
      opacity: reveal,
    }}>
      <div style={{
        fontSize: fit,
        lineHeight: 1.35,
        fontWeight: math ? 500 : 600,
        color: math ? color : theme.text,
        fontFamily: math ? '"Cambria Math", "Times New Roman", serif' : theme.fontFamily,
        letterSpacing: math ? 0.5 : theme.letterSpacing * 0.5,
        overflowWrap: 'anywhere',
        wordBreak: 'break-word',
        maxWidth: '100%',
        maxHeight: '100%',
        overflow: 'hidden',
        textAlign: math ? 'center' : 'left',
        background: math ? `${theme.surface}e6` : 'transparent',
        borderLeft: math ? 'none' : `4px solid ${color}`,
        borderRadius: math ? theme.radius : 0,
        padding: math ? '14px 20px' : '0 0 0 16px',
        boxShadow: math ? '0 12px 40px #0006' : 'none',
      }}>
        {math ? tokenize(layer.text) : layer.text}
      </div>
    </div>
  );
};