import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {openBrowser, selectComposition, renderMedia, renderStill} from '@remotion/renderer';

const here = path.dirname(fileURLToPath(import.meta.url));
const spec = JSON.parse(await fs.readFile(process.argv[2], 'utf8'));
const bundleTarget = path.resolve(path.dirname(spec.result), '.render-bundle');
let browser;
let bundlePath;
let result = {};
try {result = JSON.parse(await fs.readFile(spec.result, 'utf8'));} catch { /* First run. */ }
const digest = (value) => createHash('sha256').update(value).digest('hex');
const fileDigest = async (name) => digest(await fs.readFile(name));
try {
  bundlePath = await bundle({entryPoint: path.join(here, 'src/index.ts'), publicDir: spec.assets, outDir: bundleTarget});
  if (!spec.browser) {
    throw new Error('未找到 Chrome/Edge 可执行文件：请设置 MOVELYTH_BROWSER，不会静默下载浏览器');
  }
  browser = await openBrowser('chrome', {browserExecutable: spec.browser});
  for (const cut of spec.cuts) {
    const fingerprint = digest(JSON.stringify({props: cut.props, composition: cut.composition, version: spec.version}));
    const previous = result[cut.name];
    if (previous?.fingerprint === fingerprint && previous.hashes) {
      let valid = true;
      for (const [name, hash] of Object.entries(previous.hashes)) {
        try {if (await fileDigest(name) !== hash) valid = false;} catch {valid = false;}
      }
      if (valid) {console.log(JSON.stringify({event: 'cut_cached', cut: cut.name})); continue;}
    }
    const common = {serveUrl: bundlePath, inputProps: cut.props, puppeteerInstance: browser, logLevel: 'warn'};
    const composition = await selectComposition({...common, id: cut.composition});
    await fs.mkdir(cut.output, {recursive: true});
    const video = path.join(cut.output, 'silent.mp4');
    const stills = [];
    let offset = 0;
    for (let i = 0; i < cut.props.scenes.length; i++) {
      const scene = cut.props.scenes[i];
      // Sample late enough that appear/draw actions have finished: a review still
      // taken at 55% could show an intentionally half-built scene.
      // Sample after every appear/draw action has finished (plus a small margin) so a
      // review still never shows a deliberately half-built scene, but before the fade-out.
      const actions = scene.actions_resolved || [];
      const lastAction = actions.reduce((max, action) => Math.max(max, action.to || 0), 0);
      const sampleAt = Math.min(0.96, Math.max(0.55, lastAction + 0.04));
      const frame = Math.min(composition.durationInFrames - 1, offset + Math.floor(scene.frames * sampleAt));
      const output = path.join(cut.output, `scene-${String(i + 1).padStart(2, '0')}.jpg`);
      await renderStill({...common, composition, output, frame, imageFormat: 'jpeg', scale: 0.5});
      stills.push(output);
      offset += scene.frames;
    }
    const coverProps = {...cut.props, cover: true};
    const coverComp = await selectComposition({...common, inputProps: coverProps, id: cut.composition});
    const cover = path.join(cut.output, 'cover.png');
    await renderStill({...common, composition: coverComp, inputProps: coverProps, output: cover, frame: 45});
    if (spec.stillsOnly) {
      let preview;
      if (spec.previewSeconds) {
        preview = path.join(cut.output, 'preview.mp4');
        const lastFrame = Math.min(composition.durationInFrames - 1,
          Math.max(1, Math.round(spec.previewSeconds * composition.fps) - 1));
        console.log(JSON.stringify({event: 'preview_start', cut: cut.name, seconds: spec.previewSeconds}));
        await renderMedia({...common, composition, codec: 'h264', outputLocation: preview,
          scale: spec.scale ?? 0.5, frameRange: [0, lastFrame], concurrency: spec.concurrency,
          crf: 23, x264Preset: 'veryfast', pixelFormat: 'yuv420p', disableSharedMemoryCapture: true,
          mediaCacheSizeInBytes: 128 * 1024 * 1024, offthreadVideoCacheSizeInBytes: 128 * 1024 * 1024,
          offthreadVideoThreads: 1});
      }
      result[cut.name] = {cover, stills, preview, frames: composition.durationInFrames,
        width: composition.width, height: composition.height, fps: composition.fps};
      await fs.writeFile(spec.result, JSON.stringify(result, null, 2));
      continue;
    }
    let animatic;
    if (spec.animaticScale) {
      // Full-length, low-resolution animatic with the real voice, captions, pauses,
      // sound events and transitions — not a teaser of the opening seconds.
      animatic = path.join(cut.output, 'animatic.mp4');
      console.log(JSON.stringify({event: 'animatic_start', cut: cut.name, frames: composition.durationInFrames}));
      await renderMedia({...common, composition, codec: 'h264', outputLocation: animatic,
        scale: spec.animaticScale, crf: 30, x264Preset: 'veryfast', pixelFormat: 'yuv420p',
        concurrency: spec.concurrency, disableSharedMemoryCapture: true,
        mediaCacheSizeInBytes: 128 * 1024 * 1024, offthreadVideoCacheSizeInBytes: 128 * 1024 * 1024,
        offthreadVideoThreads: 1});
    }
    console.log(JSON.stringify({event: 'render_start', cut: cut.name, frames: composition.durationInFrames}));
    let last = -1;
    await renderMedia({...common, composition, codec: 'h264', outputLocation: video,
      concurrency: spec.concurrency, crf: 19, x264Preset: 'veryfast', pixelFormat: 'yuv420p', disableSharedMemoryCapture: true,
      mediaCacheSizeInBytes: 128 * 1024 * 1024, offthreadVideoCacheSizeInBytes: 128 * 1024 * 1024,
      offthreadVideoThreads: 1, ffmpegOverride: ({args}) => {
        const result = [...args];
        const index = result.indexOf('-threads');
        if (index >= 0) result[index + 1] = '2';
        else result.splice(result.length - 1, 0, '-threads', '2');
        return result;
      },
      onProgress: ({progress}) => {const bucket = Math.floor(progress * 10); if (bucket !== last) {console.log(JSON.stringify({event: 'progress', cut: cut.name, percent: bucket * 10})); last = bucket;}}});
    const hashes = {};
    for (const filename of [video, cover, animatic, ...stills].filter(Boolean)) hashes[filename] = await fileDigest(filename);
    result[cut.name] = {video, cover, animatic, stills, frames: composition.durationInFrames, width: composition.width, height: composition.height, fps: composition.fps, fingerprint, hashes};
    await fs.writeFile(spec.result, JSON.stringify(result, null, 2));
  }
} finally {
  if (browser) await browser.close({silent: true});
  if (bundlePath && path.resolve(bundlePath) === bundleTarget &&
      bundleTarget.startsWith(path.resolve(path.dirname(spec.result)) + path.sep)) {
    await fs.rm(bundleTarget, {recursive: true, force: true});
  }
}
