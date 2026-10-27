import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Caption, MovieProps, Scene} from './types';
import {SceneStage} from './Stage';
import {captionBand, fitFont, footerBand, headingBand, labelBand, measureText, safeMargin} from './layouts';
import {accent, clamp, easeOut, themeFor} from './theme';
import type {Theme} from './theme';

const locate = (scenes: Scene[], frame: number): {index: number; local: number} => {
  let offset = 0;
  for (let i = 0; i < scenes.length; i++) {
    if (frame < offset + scenes[i].frames) return {index: i, local: frame - offset};
    offset += scenes[i].frames;
  }
  const last = scenes.length - 1;
  return {index: last, local: Math.max(0, scenes[last].frames - 1)};
};

/**
 * How long each hand-over lasts, in seconds.
 *
 * The incoming scene animates over the outgoing one, which stays on screen until
 * the hand-over finishes.  V1 rendered only the current scene, so a "wipe" was
 * really a fragment of the new scene appearing over the background — the outgoing
 * picture had already vanished.  Durations are short on purpose: a long dissolve
 * reads as a slide deck.
 */
const TRANSITION_SECONDS: Record<string, number> = {
  cut: 0,
  fade: 0.40,
  slide: 0.46,
  wipe: 0.44,
  dip: 0.52,
  zoom: 0.48,
};

const isCut = (scene: Scene): boolean => (scene.transition || 'fade') === 'cut';

/** Incoming transform/clip at *enter* (0 = just started, 1 = settled). */
const enterStyle = (scene: Scene, enter: number): React.CSSProperties => {
  switch (scene.transition || 'fade') {
    case 'slide':
      return {transform: `translateX(${(1 - enter) * 100}%)`};
    case 'wipe':
      // A feathered directional reveal: a hard edge cutting two different layouts
      // looks like a broken slide, while a soft edge reads as one picture becoming
      // another.  The mask moves with the transition and the outgoing scene fades.
      return {
        maskImage: `linear-gradient(90deg, #000 ${Math.max(0, enter * 140 - 40)}%,`
          + ` transparent ${Math.min(100, enter * 140)}%)`,
        WebkitMaskImage: `linear-gradient(90deg, #000 ${Math.max(0, enter * 140 - 40)}%,`
          + ` transparent ${Math.min(100, enter * 140)}%)`,
      };
    case 'zoom':
      return {opacity: Math.min(1, enter * 1.3), transform: `scale(${1.05 - 0.05 * enter})`};
    case 'dip':
      return {opacity: enter};
    case 'fade':
    default:
      return {opacity: enter};
  }
};

/**
 * How the outgoing scene behaves while the new one enters.
 *
 * A wipe or slide that merely reveals the new frame *over* the old one puts two
 * headlines in the same place for a third of a second — the exact "mechanical
 * cut" this pass is meant to remove.  So a wipe tiles the two scenes instead of
 * overlapping them, a slide lets the incoming frame push across the old one, and
 * a fade/dip/zoom fades the old one out slightly faster than the new one arrives.
 */
const outgoingStyle = (scene: Scene, enter: number): React.CSSProperties => {
  switch (scene.transition || 'fade') {
    case 'wipe':
      // The outgoing scene fades under the feathered reveal, so the seam never shows
      // two headlines at once.
      return {opacity: Math.max(0, 1 - Math.pow(enter, 0.7) * 1.25)};
    case 'slide':
      return {opacity: Math.min(1, (1 - enter) * 2.2)};
    case 'zoom':
      return {opacity: Math.max(0, 1 - Math.pow(enter, 0.65) * 1.15)};
    case 'fade':
    case 'dip':
      return {opacity: Math.max(0, 1 - enter)};
    case 'cut':
    default:
      return {opacity: 0};
  }
};

const isIllustrative = (scene: Scene): boolean =>
  scene.layers.some((layer) => layer.type === 'diagram') ||
  scene.layers.some((layer) => layer.type === 'procedural' && ['network', 'wave', 'orbit'].includes(layer.procedural)) ||
  scene.layers.some((layer) => layer.type === 'chart' && layer.source_note.length > 0);

const captionSize = (text: string, base: number, vertical: boolean): number => {
  if (text.length > 30) return Math.round(base * 0.8);
  if (text.length > 22) return Math.round(base * 0.88);
  return vertical ? Math.round(base * 1.02) : base;
};

/** Karaoke: spoken words bright, the current word in the accent colour. */
const CaptionLine: React.FC<{caption: Caption; time: number; theme: Theme; color: string;
  size: number; emphasis: string[]}> = ({caption, time, theme, color, size, emphasis}) => {
  const words = caption.words && caption.words.length ? caption.words : null;
  if (!words) {
    return <span style={{fontSize: size}}>{caption.text}</span>;
  }
  return <span style={{fontSize: size}}>
    {words.map((word, index) => {
      const spoken = time >= word.start;
      const current = time >= word.start && time < word.end;
      const marked = emphasis.some((key) => key && word.text.includes(key));
      return <span key={`${word.text}-${index}`} style={{
        color: current ? color : spoken ? theme.text : `${theme.text}88`,
        fontWeight: marked || current ? 700 : 500,
        // A soft lift, not a neon halo: a large blurred glow behind one word made
        // the caption look out of focus on a dark background.
        textShadow: current ? `0 0 10px ${color}33` : undefined,
      }}>{word.text}</span>;
    })}
  </span>;
};

const lineCount = (text: string, width: number, size: number): number => {
  let rows = 0;
  for (const paragraph of text.split('\n')) {
    let used = 0;
    let count = 1;
    for (const ch of paragraph) {
      const w = measureText(ch, size);
      if (used + w > width && used > 0) {
        count += 1;
        used = w;
      } else {
        used += w;
      }
    }
    rows += count;
  }
  return Math.max(1, rows);
};

/**
 * Heading + labels as one flow.
 *
 * V1 pinned the labels to a fixed band at y≈690 while the heading only filled the
 * top of its 300 px band, which is why every landscape frame had a 400 px hole in
 * the left column.  Flowing them means the labels always sit directly under the
 * heading, and the whole block stays inside the reserved area (so it cannot cover
 * the visual), with the label font shrunk if the block runs out of room.
 */
const TextColumn: React.FC<{scene: Scene; index: number; total: number; theme: Theme;
  vertical: boolean; layout: string; opacity: number; rise: number}> =
({scene, index, total, theme, vertical, layout, opacity, rise}) => {
  const headingBox = headingBand(vertical, layout);
  const labelBox = labelBand(vertical, layout);
  const base = vertical ? theme.type.heading * 0.86 : theme.type.heading;
  const size = fitFont(scene.heading, headingBox, base, vertical ? 40 : 46, 1.24);
  const rows = lineCount(scene.heading, headingBox.w, size);
  const kicker = theme.type.micro * 1.6 + (vertical ? 22 : 20);
  const headingHeight = kicker + rows * size * 1.24;
  const gap = vertical ? 26 : 24;
  const unionBottom = Math.max(headingBox.y + headingBox.h, labelBox.y + labelBox.h);
  const available = Math.max(40, unionBottom - headingBox.y - headingHeight - gap);
  const labels = scene.labels;
  const labelSize = labels.length
    ? fitFont(labels.join(''), {x: 0, y: 0, w: headingBox.w, h: available},
      theme.type.label, 20, 1.5)
    : theme.type.label;
  const color = accent[scene.color] || theme.text;
  const row = !vertical && layout !== 'diagram';
  return <div style={{position: 'absolute', left: headingBox.x, top: headingBox.y,
    width: headingBox.w, height: unionBottom - headingBox.y, opacity,
    display: 'flex', flexDirection: 'column', justifyContent: 'flex-start',
    transform: `translateY(${rise}px)`}}>
    <div style={{display: 'flex', alignItems: 'center', gap: 16, marginBottom: vertical ? 22 : 20,
      flexShrink: 0}}>
      <div style={{width: 56, height: 4, borderRadius: 4, background: color}}/>
      <div style={{fontSize: theme.type.micro, letterSpacing: 4, color: theme.faint, fontWeight: 600}}>
        {String(index + 1).padStart(2, '0')} / {String(total).padStart(2, '0')}
      </div>
    </div>
    <div style={{fontSize: size, lineHeight: 1.24, fontWeight: theme.headingWeight,
      letterSpacing: theme.letterSpacing, overflowWrap: 'anywhere', wordBreak: 'break-word',
      fontFamily: theme.fontFamilyDisplay, textShadow: '0 2px 24px #00000055', flexShrink: 0}}>
      {scene.heading}
    </div>
    {labels.length > 0 && <div style={{marginTop: gap, display: 'flex', gap: row ? 26 : 10,
      flexDirection: row ? 'row' : 'column', flexWrap: 'wrap', alignContent: 'flex-start',
      alignItems: row ? 'center' : 'flex-start', overflow: 'hidden'}}>
      {labels.map((label, i) => <div key={label} style={{fontSize: labelSize,
        color: i === 0 ? color : theme.muted,
        borderLeft: `3px solid ${i === 0 ? color : `${theme.faint}88`}`,
        padding: '2px 0 2px 14px', fontWeight: i === 0 ? 600 : 500,
        maxWidth: '100%', overflowWrap: 'anywhere', lineHeight: 1.45}}>
        {label}
      </div>)}
    </div>}
  </div>;
};

/** One scene as it appears at a given local frame, without any transition applied. */
const SceneBody: React.FC<{scene: Scene; index: number; total: number; local: number; fps: number;
  layout: string; theme: Theme; vertical: boolean; layers: string[]; time: number}> =
({scene, index, total, local, fps, layout, theme, vertical, layers, time}) => {
  const progress = clamp(local / Math.max(1, scene.frames - 1));
  const color = accent[scene.color] || accent.cyan;
  const band = captionBand(vertical);
  const footer = footerBand(vertical);
  const margin = safeMargin(vertical);
  const seconds = local / fps;
  const caption = scene.captions.find((page) => seconds >= page.start && seconds < page.end);
  const headingOpacity = clamp(local / (0.3 * fps));
  const rise = 16 * (1 - easeOut(clamp(local / (0.45 * fps))));
  return <>
    <SceneStage scene={scene} layout={layout} time={time} progress={progress}
      layers={layers} vertical={vertical} theme={theme}/>
    {/* A readable scrim under the headline.  Without it a bright chart behind the
        title made the text unreadable on the immersive layout; it is drawn only
        over the text area (above the hero band), so the visual keeps its contrast. */}
    {layout === 'immersive' && <div style={{
      position: 'absolute', left: 0, top: 0, width: '100%',
      height: vertical ? '27%' : '35%',
      background: `linear-gradient(180deg, ${theme.backgroundBase}ee 0%,`
        + ` ${theme.backgroundBase}bb 70%, ${theme.backgroundBase}00 100%)`,
    }}/>}
    <TextColumn scene={scene} index={index} total={total} theme={theme} vertical={vertical}
      layout={layout} opacity={headingOpacity} rise={rise}/>
    {caption && <div style={{position: 'absolute', left: margin + 20, right: margin + 20,
      top: band.top, height: band.bottom - band.top, display: 'flex', justifyContent: 'center',
      alignItems: 'center'}}>
      <div style={{fontSize: captionSize(caption.text, theme.type.caption, vertical),
        fontWeight: 500, lineHeight: 1.42, textAlign: 'center', color: theme.text,
        padding: '10px 26px', maxWidth: '92%', overflowWrap: 'anywhere',
        textShadow: '0 2px 16px #000000cc'}}>
        <CaptionLine caption={caption} time={seconds} theme={theme} color={color}
          size={captionSize(caption.text, theme.type.caption, vertical)} emphasis={scene.emphasis || []}/>
      </div>
    </div>}
  </>;
};

export const Movie: React.FC<MovieProps> = (props) => {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const vertical = height > width;
  const theme = themeFor(props.style);
  const scenes = props.scenes;
  const cover = Boolean(props.cover);
  const {index, local} = cover ? {index: 0, local: Math.round(fps * 1.5)} : locate(scenes, frame);
  const scene = scenes[index];
  const layout: string = cover ? 'cover' : scene.layout;
  const accentColor = accent[scene.color] || accent.cyan;
  const margin = safeMargin(vertical);
  const footer = footerBand(vertical);
  const progress = clamp(local / Math.max(1, scene.frames - 1));

  // Hand-over: the previous scene stays visible underneath while this one enters.
  const kind = scene.transition || 'fade';
  const window = (TRANSITION_SECONDS[kind] ?? 0) * fps;
  const enter = window > 0 ? easeOut(clamp(local / window)) : 1;
  const showPrevious = !cover && index > 0 && !isCut(scene) && local < window;
  const previous = showPrevious ? scenes[index - 1] : undefined;

  const tagline = theme.name === 'documentary' ? '知识的现场 · 逐帧解释'
    : theme.name === 'minimal' ? '从一个问题开始' : 'FROM IDEA TO FINAL CUT.';

  return <AbsoluteFill style={{background: theme.background, color: theme.text, fontFamily: theme.fontFamily}}>
    <AbsoluteFill style={{background: theme.overlay}}/>
    <div style={{position: 'absolute', inset: 0, opacity: theme.name === 'minimal' ? 0.05 : 0.1,
      backgroundImage: `linear-gradient(${theme.grid}18 1px, transparent 1px),`
        + ` linear-gradient(90deg, ${theme.grid}18 1px, transparent 1px)`,
      backgroundSize: '96px 96px'}}/>
    {/* A vignette keeps the eye in the middle of the frame and hides the grid edges. */}
    <AbsoluteFill style={{background: 'radial-gradient(ellipse 78% 72% at 50% 46%, transparent 42%, #00000055 100%)'}}/>

    {previous && <AbsoluteFill style={outgoingStyle(scene, enter)}>
      <SceneBody scene={previous} index={index - 1} total={scenes.length} local={previous.frames - 1}
        fps={fps} layout={previous.layout} theme={theme} vertical={vertical} layers={props.layers}
        time={(previous.frames - 1) / fps}/>
    </AbsoluteFill>}

    <AbsoluteFill style={cover ? {opacity: 1} : enterStyle(scene, enter)}>
      {cover ? <>
        <SceneStage scene={{...scene, layers: scene.layers.filter((layer) => layer.region === 'main')}}
          layout={layout} time={4} progress={0.62} layers={props.layers} vertical={vertical} theme={theme}/>
        {/* A soft mask on the left edge of the visual so the title column and the
            chart do not fight for the same pixels. */}
        <div style={{position: 'absolute', left: 0, top: 0, width: vertical ? '100%' : '58%',
          height: vertical ? '38%' : '100%',
          background: `linear-gradient(${vertical ? '180deg' : '90deg'},`
            + ` ${theme.backgroundBase} 12%, ${theme.backgroundBase}00 100%)`}}/>
        <div style={{position: 'absolute', left: vertical ? 70 : 96, top: vertical ? 240 : 200,
          width: vertical ? 940 : 780}}>
          <div style={{width: 72, height: 5, borderRadius: 5, background: accentColor, marginBottom: 28}}/>
          <div style={{fontSize: fitFont(props.title, {x: 0, y: 0, w: vertical ? 940 : 780, h: 330},
            vertical ? Math.round(theme.type.display * 0.78) : Math.round(theme.type.display * 0.8),
            42, 1.18), lineHeight: 1.18, fontWeight: theme.headingWeight,
            letterSpacing: theme.letterSpacing, fontFamily: theme.fontFamilyDisplay}}>{props.title}</div>
          <div style={{fontSize: vertical ? 30 : 28, letterSpacing: 3, color: theme.muted, marginTop: 26}}>
            {props.coverCaption || tagline}
          </div>
        </div>
      </> : <SceneBody scene={scene} index={index} total={scenes.length} local={local} fps={fps}
        layout={layout} theme={theme} vertical={vertical} layers={props.layers} time={local / fps}/>}
    </AbsoluteFill>

    {/* A dip goes through black: the incoming scene is already opaque at mid-point,
        so the darkening has to be drawn on top of both. */}
    {!cover && kind === 'dip' && local < window && <AbsoluteFill style={{
      background: '#000',
      opacity: 0.85 * Math.sin(Math.PI * clamp(local / window)),
    }}/>}

    <div style={{position: 'absolute', top: vertical ? 92 : 56, left: margin, fontSize: vertical ? 26 : 24,
      letterSpacing: 4, color: theme.muted, fontWeight: 600}}>
      MOVELYTH <span style={{color: accentColor}}>幕绎</span>
    </div>
    <div style={{position: 'absolute', top: vertical ? 96 : 58, right: margin, fontSize: 20, color: theme.faint,
      letterSpacing: 2}}>{props.episode}</div>
    <div style={{position: 'absolute', top: vertical ? 138 : 92, left: margin, right: margin, height: 1,
      background: `${theme.grid}22`}}/>

    <div style={{position: 'absolute', left: margin, right: margin, top: footer.top,
      fontSize: vertical ? 19 : 18, lineHeight: 1.5, color: theme.faint, display: 'flex',
      justifyContent: 'space-between', gap: 24}}>
      <span style={{overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>
        {cover ? (theme.name === 'documentary' ? '数学与科学 · 看见结构的力量' : 'Movelyth · 幕绎')
          : `来源：${(props.sources[scene.source_index]?.label || '原理演示').slice(0, 60)}`}
      </span>
      {!cover && isIllustrative(scene) && <span style={{flexShrink: 0}}>原理示意</span>}
    </div>

    {/* Progress rail with a tick per chapter: the viewer can see where they are. */}
    <div style={{position: 'absolute', bottom: 0, left: 0, right: 0, height: 4,
      background: `${theme.grid}1f`}}>
      <div style={{height: '100%', width: `${(index + progress) / scenes.length * 100}%`,
        background: `linear-gradient(90deg, ${accentColor}66, ${accentColor})`}}/>
    </div>
    <div style={{position: 'absolute', bottom: 0, left: 0, right: 0, height: 4, display: 'flex'}}>
      {scenes.map((item, i) => <div key={item.id} style={{width: `${100 / scenes.length}%`,
        borderRight: i < scenes.length - 1 ? `2px solid ${theme.backgroundBase}` : undefined}}/>)}
    </div>
  </AbsoluteFill>;
};
