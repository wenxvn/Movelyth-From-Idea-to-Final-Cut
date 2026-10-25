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
  browser = await openBrowser('chrome', spec.browser ? {browserExecutable: spec.browser} : {});
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
      const frame = Math.min(composition.durationInFrames - 1, offset + Math.floor(scene.frames * 0.55));
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
      result[cut.name] = {cover, stills, frames: composition.durationInFrames, width: composition.width, height: composition.height, fps: composition.fps};
      await fs.writeFile(spec.result, JSON.stringify(result, null, 2));
      continue;
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
    for (const filename of [video, cover, ...stills]) hashes[filename] = await fileDigest(filename);
    result[cut.name] = {video, cover, stills, frames: composition.durationInFrames, width: composition.width, height: composition.height, fps: composition.fps, fingerprint, hashes};
    await fs.writeFile(spec.result, JSON.stringify(result, null, 2));
  }
} finally {
  if (browser) await browser.close({silent: true});
  if (bundlePath && path.resolve(bundlePath) === bundleTarget &&
      bundleTarget.startsWith(path.resolve(path.dirname(spec.result)) + path.sep)) {
    await fs.rm(bundleTarget, {recursive: true, force: true});
  }
}
