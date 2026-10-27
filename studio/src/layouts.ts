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

/** Full-bleed layers: only `full`, which is a background texture, not content. */
export const isFullBleed = (_layout: string, region: Region): boolean => region === 'full';

/**
 * Advance width of one character in em.  A CJK glyph is one em; Latin letters,
 * digits and punctuation are narrower, and treating them as full-width was why a
 * line like "det A = a·d − b·c" was shrunk far more than necessary.
 */
const charEm = (ch: string): number => {
  const code = ch.codePointAt(0) ?? 0;
  if (code < 0x2000) return 0.56;
  if (code >= 0x3000 && code <= 0x9fff) return 1;
  if (code >= 0xff00) return 1;
  return 0.62;
};

const textEm = (text: string): number => {
  let total = 0;
  for (const ch of text) total += charEm(ch);
  return total;
};

/** Advance width of *text* at *size* px.  Used to size label chips so text never overflows them. */
export const measureText = (text: string, size: number): number => Math.ceil(textEm(text) * size);

/**
 * Largest size (down to *min*) whose wrapped text still fits the box.
 *
 * Deterministic: only the string, the box and the base size are used, so renders
 * are reproducible.  Measured in em widths instead of character counts, so mixed
 * Chinese/Latin text is neither clipped nor shrunk to half size.
 */
export const fitFont = (text: string, box: Box, base: number, min: number, lineHeight = 1.26): number => {
  const paragraphs = text.split('\n');
  let size = base;
  while (size > min) {
    let rows = 0;
    for (const paragraph of paragraphs) {
      let line = 0;
      let lines = 1;
      for (const ch of paragraph) {
        const width = charEm(ch) * size * 1.02;
        if (line + width > box.w && line > 0) {
          lines += 1;
          line = width;
        } else {
          line += width;
        }
      }
      rows += lines;
    }
    if (rows * size * lineHeight <= box.h) return size;
    size -= 2;
  }
  return min;
};

/** Split a heading into at most two visual rows at a sensible boundary. */
export const balanceHeading = (text: string): string => {
  if (text.length <= 8 || text.includes('\n')) return text;
  const mid = Math.round(text.length / 2);
  const candidates: number[] = [];
  for (let i = 4; i <= text.length - 4; i++) {
    if ('，、；：。！？·—'.includes(text[i - 1])) candidates.push(i);
  }
  const split = candidates.sort((a, b) => Math.abs(a - mid) - Math.abs(b - mid))[0];
  if (split === undefined || split < 3 || text.length - split < 3) return text;
  return `${text.slice(0, split)}\n${text.slice(split)}`;
};
