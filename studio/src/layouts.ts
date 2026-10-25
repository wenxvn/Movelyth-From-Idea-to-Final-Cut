import contract from './generated/layout.json';
import type {LayoutKind, Region} from './types';

export type Box = {x: number; y: number; w: number; h: number};

const layouts = contract.layouts as unknown as Record<string, Record<string, Record<string, Box>>>;
const headingBands = contract.heading_bands as unknown as Record<string, Record<string, Box>>;
const labelBands = contract.label_bands as unknown as Record<string, Record<string, Box>>;
const captionBands = contract.caption_bands as unknown as Record<string, {top: number; bottom: number}>;
const footerBands = contract.footer_bands as unknown as Record<string, {top: number; bottom: number}>;

export const orientation = (vertical: boolean): string => (vertical ? 'portrait' : 'landscape');

const pick = (set: Record<string, Box>, layout: LayoutKind | string): Box => set[layout] || set.diagram;

export const regions = (vertical: boolean, layout: LayoutKind | string): Record<Region, Box> => {
  const set = layouts[orientation(vertical)];
  return (set[layout] || set.diagram) as Record<Region, Box>;
};

export const headingBand = (vertical: boolean, layout: LayoutKind | string): Box =>
  pick(headingBands[orientation(vertical)], layout);

export const labelBand = (vertical: boolean, layout: LayoutKind | string): Box =>
  pick(labelBands[orientation(vertical)], layout);

export const captionBand = (vertical: boolean): {top: number; bottom: number} =>
  captionBands[orientation(vertical)];

export const footerBand = (vertical: boolean): {top: number; bottom: number} =>
  footerBands[orientation(vertical)];

export const safeMargin = (vertical: boolean): number =>
  (contract.safe_margin as unknown as Record<string, number>)[orientation(vertical)];

/**
 * Shrink text until it fits the reserved box.  Deterministic: only the string,
 * the box and the base size are used, so renders are reproducible.
 */
export const fitFont = (text: string, box: Box, base: number, min: number, lineHeight = 1.32): number => {
  let size = base;
  while (size > min) {
    const perLine = Math.max(1, Math.floor(box.w / (size * 1.02)));
    const lines = Math.ceil(text.length / perLine);
    if (lines * size * lineHeight <= box.h) return size;
    size -= 2;
  }
  return min;
};
