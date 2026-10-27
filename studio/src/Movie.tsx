import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Caption, MovieProps, Scene} from './types';
import {SceneStage} from './Stage';
import {
  captionBand, fitFont, footerBand, headingBand, insightBand, labelBand, measureText, regions, safeMargin,
} from './layouts';
import {accent, clamp, easeOut, themeFor} from './theme';
import type {Theme} from './theme';
import {activeBeat, insightFor, sceneBeats} from './insights';
import type {Insight} from './insights';

const locate = (scenes: Scene[], frame: number): {index: number; local: number} => {
  let offset = 0;
  for (let i = 0; i < scenes.length; i++) {
    if (frame < offset + scenes[i].frames) return {index: i, local: frame - offset};
    offset += scenes[i].frames;
  }
  const last = scenes.length - 1;
  return {index: last, local: Math.max(0, scenes[last].frames - 1)};
};

const TRANSITION_SECONDS: Record<string, number> = {
  cut: 0, fade: 0.55, slide: 0.62, wipe: 0.58, dip: 0.66, zoom: 0.56,
};

const isCut = (scene: Scene): boolean => (scene.transition || 'fade') === 'cut';

const enterStyle = (scene: Scene, enter: number): React.CSSProperties => {
  switch (scene.transition || 'fade') {
    case 'slide': {
      const direction = scene.camera === 'pan_left' ? -1 : 1;
      return {transform: `translateX(${(1 - enter) * 100 * direction}%)`};
    }
    case 'wipe':
      return {
        maskImage: `linear-gradient(90deg, #000 ${Math.max(0, enter * 140 - 40)}%, transparent ${Math.min(100, enter * 140)}%)`,
        WebkitMaskImage: `linear-gradient(90deg, #000 ${Math.max(0, enter * 140 - 40)}%, transparent ${Math.min(100, enter * 140)}%)`,
      };
    case 'zoom':
      return {opacity: Math.min(1, enter * 1.3), transform: `scale(${1.04 - 0.04 * enter})`};
    case 'dip':
      return {opacity: enter};
    default:
      return {opacity: enter};
  }
};

const outgoingStyle = (scene: Scene, enter: number): React.CSSProperties => {
  switch (scene.transition || 'fade') {
    case 'wipe':
      return {opacity: Math.max(0, 1 - Math.pow(enter, 0.7) * 1.25)};
    case 'slide':
      return {opacity: Math.min(1, (1 - enter) * 2.2)};
    case 'zoom':
      return {opacity: Math.max(0, 1 - Math.pow(enter, 0.65) * 1.15), transform: `scale(${1 + 0.02 * enter})`};
    case 'fade':
    case 'dip':
      return {opacity: Math.max(0, 1 - enter)};
    default:
      return {opacity: 0};
  }
};

const isIllustrative = (scene: Scene): boolean =>
  scene.layers.some((layer) => layer.type === 'diagram') ||
  scene.layers.some((layer) => layer.type === 'procedural' && ['network', 'wave', 'orbit'].includes(layer.procedural)) ||
  scene.layers.some((layer) => layer.type === 'chart' && layer.source_note.length > 0);

const captionSize = (text: string, base: number, vertical: boolean): number => {
  if (text.length > 30) return Math.round(base * 0.82);
  if (text.length > 22) return Math.round(base * 0.9);
  return vertical ? Math.round(base * 0.96) : base;
};

const CaptionLine: React.FC<{caption: Caption; time: number; theme: Theme; color: string;
  size: number; emphasis: string[]}> = ({caption, time, theme, color, size, emphasis}) => {
  const words = caption.words && caption.words.length ? caption.words : null;
  if (!words) return <span style={{fontSize: size}}>{caption.text}</span>;
  return <span style={{fontSize: size}}>
    {words.map((word, index) => {
      const spoken = time >= word.start;
      const current = time >= word.start && time < word.end;
      const marked = emphasis.some((key) => key && word.text.includes(key));
      return <span key={`${word.text}-${index}`} style={{
        color: current ? color : spoken ? theme.text : `${theme.text}7a`,
        fontWeight: marked || current ? 800 : 600,
        background: current ? `${color}24` : undefined,
        borderRadius: 6,
        padding: current ? '0 4px' : undefined,
        textShadow: current ? `0 0 14px ${color}44` : '0 2px 14px #000000aa',
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

const ROLE_LABEL: Record<string, string> = {
  hook: '开场', mechanism: '机制', example: '例子', turn: '转折', conclusion: '收束',
};

const heroOf = (scene: Scene): string => {
  if (scene.hero) return scene.hero;
  const drawing = new Set(['chart', 'diagram', 'timeline', 'shape', 'procedural', 'image']);
  return scene.layers.find((layer) => drawing.has(layer.type) && layer.region === 'main')?.id || '';
};

const TextColumn: React.FC<{scene: Scene; index: number; total: number; theme: Theme;
  vertical: boolean; layout: string; local: number; fps: number}> =
({scene, index, total, theme, vertical, layout, local, fps}) => {
  const headingBox = headingBand(vertical, layout);
  const labelBox = labelBand(vertical, layout);
  const base = vertical ? Math.round(theme.type.heading * 0.78) : theme.type.heading;
  const size = fitFont(scene.heading, headingBox, base, vertical ? 52 : 58, 1.16);
  const rows = lineCount(scene.heading, headingBox.w, size);
  const kicker = theme.type.micro * 1.6 + (vertical ? 22 : 18);
  const headingHeight = kicker + rows * size * 1.16;
  const gap = vertical ? 22 : 18;
  const unionBottom = Math.max(headingBox.y + headingBox.h, labelBox.y + labelBox.h);
  const available = Math.max(36, unionBottom - headingBox.y - headingHeight - gap);
  const labels = scene.labels;
  const labelSize = labels.length
    ? fitFont(labels.join(''), {x: 0, y: 0, w: headingBox.w, h: available}, theme.type.label, 24, 1.42)
    : theme.type.label;
  const color = accent[scene.color] || theme.text;
  const row = !vertical && layout !== 'diagram';
  const enter = (delay: number): number => clamp((local / fps - delay) / 0.55);
  const headingIn = easeOut(enter(0.02));
  const rule = easeOut(enter(0.12));
  const chapter = scene.chapter || '';
  const role = scene.role && scene.role !== 'mechanism' ? ROLE_LABEL[scene.role] : '';
  const meta = [chapter, role].filter(Boolean).join(' · ');
  return <div style={{position: 'absolute', left: headingBox.x, top: headingBox.y,
    width: headingBox.w, height: unionBottom - headingBox.y,
    display: 'flex', flexDirection: 'column', justifyContent: 'flex-start'}}>
    <div style={{display: 'flex', alignItems: 'center', gap: 18, marginBottom: vertical ? 18 : 16,
      flexShrink: 0, opacity: headingIn}}>
      <div style={{width: 64 * rule, height: 5, borderRadius: 4,
        background: `linear-gradient(90deg, ${color}, ${color}44)`}}/>
      <div style={{fontSize: theme.type.micro, letterSpacing: 5, color: theme.muted, fontWeight: 700}}>
        {String(index + 1).padStart(2, '0')} <span style={{color: theme.faint}}>/ {String(total).padStart(2, '0')}</span>
        {meta && <span style={{marginLeft: 16, color, letterSpacing: 2}}>{meta}</span>}
      </div>
    </div>
    <div style={{overflow: 'hidden', flexShrink: 0}}>
      <div style={{fontSize: size, lineHeight: 1.16, fontWeight: theme.headingWeight,
        letterSpacing: theme.letterSpacing, overflowWrap: 'anywhere', wordBreak: 'break-word',
        fontFamily: theme.fontFamilyDisplay, textShadow: '0 4px 30px #00000088',
        clipPath: `inset(0 ${Math.round((1 - headingIn) * 100)}% 0 0)`,
        transform: `translateY(${(1 - headingIn) * 14}px)`}}>
        {scene.heading}
      </div>
    </div>
    {labels.length > 0 && <div style={{marginTop: gap, display: 'flex', gap: row ? 14 : 10,
      flexDirection: row ? 'row' : 'column', flexWrap: 'wrap', alignContent: 'flex-start',
      alignItems: row ? 'center' : 'flex-start', overflow: 'hidden'}}>
      {labels.map((label, i) => {
        const chipIn = easeOut(clamp((local / fps - 0.26 - i * 0.08) / 0.5));
        return <div key={label} style={{fontSize: labelSize,
          color: i === 0 ? color : theme.text,
          background: i === 0 ? `${color}16` : `${theme.surface}b8`,
          border: `1px solid ${i === 0 ? `${color}66` : `${theme.grid}26`}`,
          borderLeft: `5px solid ${i === 0 ? color : `${theme.faint}99`}`,
          borderRadius: 12, padding: '10px 16px',
          fontWeight: i === 0 ? 700 : 600,
          maxWidth: '100%', overflowWrap: 'anywhere', lineHeight: 1.38,
          opacity: chipIn, transform: `translateY(${(1 - chipIn) * 10}px)`}}>
          {label}
        </div>;
      })}
    </div>}
    <div style={{marginTop: 'auto', height: 2, width: `${Math.round(rule * 100)}%`,
      background: `linear-gradient(90deg, ${color}88, transparent)`}}/>
  </div>;
};

const insightBox = (scene: Scene, vertical: boolean, layout: string): {x: number; y: number; w: number; h: number} => {
  const base = insightBand(vertical, layout);
  // If the model left the small `bottom` region empty, the card may grow upward:
  // a 140 px card floating at the bottom of a 300 px hole was still a hole.
  const hasBottom = scene.layers.some((layer) => layer.region === 'bottom' || layer.region === 'annotation');
  if (!vertical && layout === 'diagram' && !hasBottom) return {...base, y: 550, h: 330};
  return base;
};

const InsightCard: React.FC<{insight: Insight; scene: Scene; theme: Theme; vertical: boolean;
  box: {x: number; y: number; w: number; h: number}; local: number; fps: number; beat: number}> =
({insight, scene, theme, vertical, box, local, fps, beat}) => {
  if (box.h < 42) return null;
  const color = accent[scene.color] || theme.text;
  const beatStart = sceneBeats(scene)[beat]?.start ?? 0;
  const p = easeOut(clamp((local / fps - beatStart) / 0.5));
  // A 140 px band is enough for a 64 px number plus two lines of text only if
  // the card is laid out as a row; a column would clip the label silently.
  // 180 px is still a row card: a 80 px number plus two lines of 30 px text
  // needs ~196 px in a column and was silently clipped at the top and bottom.
  const compact = box.h < 210;
  const valueSize = compact ? (vertical ? 62 : 58) : (vertical ? 84 : 80);
  const labelSize = compact ? 30 : (vertical ? 34 : 32);
  const detailSize = compact ? 23 : 30;
  const steps = scene.layers.find((layer) => layer.type === 'timeline' || layer.type === 'diagram')?.steps || [];
  const numeric = /^-?\d+(?:\.\d+)?[%％]?$/.test(insight.value);
  const number = numeric ? Number(insight.value.replace(/[%％]$/, '')) : 0;
  const shown = numeric ? (number * p).toFixed(Math.abs(number) < 10 && !Number.isInteger(number) ? 2 : 0) : insight.value;
  return <div style={{position: 'absolute', left: box.x, top: box.y, width: box.w, height: box.h,
    opacity: p, transform: `translateY(${(1 - p) * 12}px)`,
    display: 'flex', flexDirection: compact ? 'row' : 'column', alignItems: compact ? 'center' : 'flex-start',
    justifyContent: 'center', gap: compact ? 20 : 6,
    padding: compact ? '0 18px' : (vertical ? '16px 24px' : '14px 22px'),
    background: `linear-gradient(135deg, ${theme.surface}e8, ${theme.backgroundBase}d8)`,
    border: `1px solid ${color}44`, borderLeft: `7px solid ${color}`,
    borderRadius: 16, boxShadow: `0 18px 60px #00000055, inset 0 0 40px ${color}08`,
    overflow: 'hidden'}}>
    <div style={{position: 'absolute', right: -30, top: -40, width: 160, height: 160,
      borderRadius: '50%', background: `radial-gradient(circle, ${color}22, transparent 70%)`}}/>
    <div style={{fontSize: valueSize, lineHeight: 1, fontWeight: 800, color,
      fontFamily: theme.fontFamilyDisplay, letterSpacing: 0.5,
      fontVariantNumeric: 'tabular-nums', textShadow: `0 0 26px ${color}33`}}>
      {shown}{numeric && /[%％]$/.test(insight.value) ? insight.value.slice(-1) : ''}
    </div>
    {compact ? <div style={{display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0}}>
      <div style={{fontSize: labelSize, fontWeight: 700, color: theme.text, lineHeight: 1.22,
        maxWidth: '100%', overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2,
        WebkitBoxOrient: 'vertical'}}>{insight.label}</div>
      <div style={{fontSize: detailSize, color: theme.muted, lineHeight: 1.22,
        maxWidth: '100%', overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2,
        WebkitBoxOrient: 'vertical'}}>{insight.detail}</div>
    </div> : <>
      <div style={{fontSize: labelSize, fontWeight: 700, color: theme.text, lineHeight: 1.25,
        maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis'}}>{insight.label}</div>
      <div style={{fontSize: detailSize, color: theme.muted, lineHeight: 1.35,
        maxWidth: '100%', overflow: 'hidden'}}>{insight.detail}</div>
      {!compact && steps.length > 1 && <div style={{display: 'flex', gap: 8, marginTop: 14,
        flexWrap: 'wrap', alignItems: 'center'}}>
        {steps.map((step, index) => <div key={step} style={{display: 'flex', alignItems: 'center', gap: 8}}>
          <div style={{width: 11, height: 11, borderRadius: '50%',
            background: index <= beat % steps.length ? color : `${theme.grid}55`,
            boxShadow: index === beat % steps.length ? `0 0 12px ${color}88` : undefined}}/>
          <span style={{fontSize: 21, color: index === beat % steps.length ? theme.text : theme.faint}}>{step}</span>
          {index < steps.length - 1 && <span style={{width: 18, height: 1, background: `${theme.grid}55`}}/>}
        </div>)}
      </div>}
    </>}
  </div>;
};

const Grain: React.FC<{frame: number}> = ({frame}) => {
  const x = (frame * 7) % 11;
  const y = (frame * 5) % 13;
  // Fine grain is expensive to encode (the V3 first render was 80 MB vs V2's
  // 19 MB) and reads as noise on a phone.  A coarser, softer pattern keeps the
  // gradient from banding without turning into static.
  return <AbsoluteFill style={{pointerEvents: 'none', opacity: 0.10, mixBlendMode: 'overlay',
    backgroundImage: 'radial-gradient(#ffffff 0.7px, transparent 0.9px), radial-gradient(#000000 0.7px, transparent 0.9px)',
    backgroundSize: '5px 5px, 7px 7px', backgroundPosition: `${x}px ${y}px, ${y}px ${x}px`}}/>;
};

const SceneBody: React.FC<{scene: Scene; index: number; total: number; local: number; fps: number;
  layout: string; theme: Theme; vertical: boolean; layers: string[]; time: number; cover?: boolean}> =
({scene, index, total, local, fps, layout, theme, vertical, layers, time, cover = false}) => {
  const progress = clamp(local / Math.max(1, scene.frames - 1));
  const color = accent[scene.color] || accent.cyan;
  const band = captionBand(vertical);
  const margin = safeMargin(vertical);
  const seconds = local / fps;
  const caption = scene.captions.find((page) => seconds >= page.start && seconds < page.end);
  const beats = sceneBeats(scene);
  const beat = activeBeat(beats, seconds);
  const insight = insightFor(scene, beat, beats);
  const main = regions(vertical, layout).main;
  const hero = heroOf(scene);
  return <>
    {main && <div style={{position: 'absolute', left: main.x - 60, top: main.y - 60,
      width: main.w + 120, height: main.h + 120,
      background: `radial-gradient(ellipse 52% 48% at 50% 50%, ${color}1f, transparent 72%)`,
      pointerEvents: 'none'}}/>}
    <SceneStage scene={scene} layout={layout} time={time} progress={progress}
      layers={layers} vertical={vertical} theme={theme} beat={beat} beats={beats} heroId={hero}/>
    {layout === 'immersive' && <div style={{
      position: 'absolute', left: 0, top: 0, width: '100%', height: vertical ? '26%' : '34%',
      background: `linear-gradient(180deg, ${theme.backgroundBase}ee 0%, ${theme.backgroundBase}bb 70%, ${theme.backgroundBase}00 100%)`,
    }}/>}
    {!cover && <TextColumn scene={scene} index={index} total={total} theme={theme} vertical={vertical}
      layout={layout} local={local} fps={fps}/>}
    {!cover && insight && (layout !== 'immersive' || Boolean(scene.takeaway || scene.metric))
      && <InsightCard insight={insight} scene={scene} theme={theme} vertical={vertical}
        box={insightBox(scene, vertical, layout)} local={local} fps={fps} beat={beat}/>}
    {caption && !cover && <div style={{position: 'absolute', left: 0, right: 0,
      top: band.top - 52, height: band.bottom - band.top + 52,
      background: `linear-gradient(180deg, ${theme.backgroundBase}00, ${theme.backgroundBase}d9 42%, ${theme.backgroundBase}f2 100%)`,
      pointerEvents: 'none'}}/>}
    {caption && !cover && <div style={{position: 'absolute', left: margin + 20, right: margin + 20,
      top: band.top, height: band.bottom - band.top, display: 'flex', justifyContent: 'center', alignItems: 'center'}}>
      <div style={{fontSize: captionSize(caption.text, theme.type.caption, vertical),
        fontWeight: 600, lineHeight: 1.34, textAlign: 'center', color: theme.text,
        padding: '8px 26px', maxWidth: '94%', overflowWrap: 'anywhere',
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
  const progress = clamp(local / Math.max(1, scene.frames - 1));

  const kind = scene.transition || 'fade';
  const window = (TRANSITION_SECONDS[kind] ?? 0) * fps;
  const enter = window > 0 ? easeOut(clamp(local / window)) : 1;
  const showPrevious = !cover && index > 0 && !isCut(scene) && local < window;
  const previous = showPrevious ? scenes[index - 1] : undefined;
  const tagline = theme.name === 'documentary' ? '知识的现场 · 逐帧解释'
    : theme.name === 'minimal' ? '从一个问题开始' : 'FROM IDEA TO FINAL CUT.';
  const coverScenes = scenes.slice(0, 4);

  return <AbsoluteFill style={{background: theme.background, color: theme.text, fontFamily: theme.fontFamily}}>
    <AbsoluteFill style={{background: theme.overlay}}/>
    <AbsoluteFill style={{background: theme.mesh, transform: `translate(${Math.sin(frame / 260) * 8}px, ${Math.cos(frame / 310) * 6}px) scale(1.04)`}}/>
    <div style={{position: 'absolute', inset: -60, opacity: theme.name === 'minimal' ? 0.06 : 0.12,
      transform: `translate(${Math.sin(frame / 420) * 18}px, ${Math.cos(frame / 380) * 12}px)`,
      backgroundImage: `linear-gradient(${theme.grid}20 1px, transparent 1px), linear-gradient(90deg, ${theme.grid}20 1px, transparent 1px)`,
      backgroundSize: '96px 96px'}}/>
    <AbsoluteFill style={{background: 'radial-gradient(ellipse 78% 72% at 50% 46%, transparent 40%, #00000066 100%)'}}/>
    <Grain frame={frame}/>

    {previous && <AbsoluteFill style={outgoingStyle(scene, enter)}>
      <SceneBody scene={previous} index={index - 1} total={scenes.length} local={previous.frames - 1}
        fps={fps} layout={previous.layout} theme={theme} vertical={vertical} layers={props.layers}
        time={(previous.frames - 1) / fps}/>
    </AbsoluteFill>}

    <AbsoluteFill style={cover ? {opacity: 1} : enterStyle(scene, enter)}>
      {cover ? <>
        <SceneStage scene={{...scene, layers: scene.layers.filter((layer) => layer.region === 'main')}}
          layout={layout} time={4} progress={0.62} layers={props.layers} vertical={vertical} theme={theme}
          beat={0} beats={[]} heroId={heroOf(scene)} showAnnotations={false}/>
        <div style={{position: 'absolute', left: 0, top: 0, width: vertical ? '100%' : '62%',
          height: vertical ? '42%' : '100%',
          background: `linear-gradient(${vertical ? '180deg' : '90deg'}, ${theme.backgroundBase} 10%, ${theme.backgroundBase}cc 55%, ${theme.backgroundBase}00 100%)`}}/>
        <div style={{position: 'absolute', left: vertical ? 70 : 96, top: vertical ? 230 : 170,
          width: vertical ? 940 : 820}}>
          <div style={{display: 'flex', alignItems: 'center', gap: 18, marginBottom: 26}}>
            <div style={{width: 84, height: 6, borderRadius: 6, background: accentColor}}/>
            <div style={{fontSize: vertical ? 26 : 24, letterSpacing: 5, color: theme.muted, fontWeight: 700}}>
              科普 · 程序动画
            </div>
          </div>
          <div style={{fontSize: fitFont(props.title, {x: 0, y: 0, w: vertical ? 940 : 760, h: 360},
            vertical ? 96 : 108, 52, 1.12), lineHeight: 1.12, fontWeight: theme.headingWeight,
            letterSpacing: theme.letterSpacing, fontFamily: theme.fontFamilyDisplay,
            textShadow: '0 6px 40px #00000088'}}>{props.title}</div>
          <div style={{fontSize: 30, letterSpacing: 3, color: theme.muted, marginTop: 28, lineHeight: 1.4}}>
            {props.coverCaption || tagline}
          </div>
          <div style={{display: 'flex', gap: 12, marginTop: 34, flexWrap: 'wrap'}}>
            {coverScenes.map((item, i) => <div key={item.id} style={{fontSize: 24, color: i === 0 ? accentColor : theme.muted,
              border: `1px solid ${i === 0 ? `${accentColor}66` : `${theme.grid}2a`}`,
              background: i === 0 ? `${accentColor}14` : `${theme.surface}99`,
              borderRadius: 10, padding: '8px 14px'}}>{item.chapter || item.heading}</div>)}
          </div>
        </div>
        <div style={{position: 'absolute', left: vertical ? 70 : 96, bottom: vertical ? 120 : 86,
          fontSize: 22, color: theme.faint, letterSpacing: 2}}>来源梳理 · 程序动画 · 逐句配音</div>
      </> : <SceneBody scene={scene} index={index} total={scenes.length} local={local} fps={fps}
        layout={layout} theme={theme} vertical={vertical} layers={props.layers} time={local / fps}/>}
    </AbsoluteFill>

    {!cover && kind === 'dip' && local < window && <AbsoluteFill style={{
      background: '#000', opacity: 0.88 * Math.sin(Math.PI * clamp(local / window))}}/>}
    {!cover && !isCut(scene) && local < window && <AbsoluteFill style={{
      background: `linear-gradient(105deg, transparent 30%, ${accentColor}22 48%, transparent 66%)`,
      opacity: Math.sin(Math.PI * clamp(local / window)) * 0.7}}/>}

    <div style={{position: 'absolute', top: vertical ? 92 : 56, left: margin, fontSize: vertical ? 28 : 26,
      letterSpacing: 4, color: theme.muted, fontWeight: 700}}>
      MOVELYTH <span style={{color: accentColor}}>幕绎</span>
    </div>
    <div style={{position: 'absolute', top: vertical ? 96 : 58, right: margin, fontSize: 22, color: theme.faint,
      letterSpacing: 2}}>{props.episode}</div>
    <div style={{position: 'absolute', top: vertical ? 138 : 92, left: margin, right: margin, height: 1,
      background: `${theme.grid}26`}}/>

    <div style={{position: 'absolute', left: margin, right: margin, top: footerBand(vertical).top,
      fontSize: vertical ? 21 : 20, lineHeight: 1.5, color: theme.faint, display: 'flex',
      justifyContent: 'space-between', gap: 24}}>
      <span style={{overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>
        {cover ? (theme.name === 'documentary' ? '数学与科学 · 看见结构的力量' : 'Movelyth · 幕绎')
          : `来源：${(props.sources[scene.source_index]?.label || '原理演示').slice(0, 60)}`}
      </span>
      {!cover && isIllustrative(scene) && <span style={{flexShrink: 0}}>原理示意</span>}
    </div>

    <div style={{position: 'absolute', bottom: 0, left: 0, right: 0, height: 5, background: `${theme.grid}1f`}}>
      <div style={{height: '100%', width: `${(index + progress) / scenes.length * 100}%`,
        background: `linear-gradient(90deg, ${accentColor}66, ${accentColor})`}}/>
    </div>
    <div style={{position: 'absolute', bottom: 0, left: 0, right: 0, height: 5, display: 'flex'}}>
      {scenes.map((item, i) => <div key={item.id} style={{width: `${100 / scenes.length}%`,
        borderRight: i < scenes.length - 1 ? `2px solid ${theme.backgroundBase}` : undefined}}/>)}
    </div>
  </AbsoluteFill>;
};
