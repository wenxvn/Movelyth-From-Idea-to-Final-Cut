import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {openBrowser, renderStill, selectComposition} from '@remotion/renderer';

const specPath = process.argv[2];
const spec = JSON.parse(await fs.readFile(specPath, 'utf8'));
const studio = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(spec.output);
await fs.mkdir(outDir, {recursive: true});
const bundlePath = await bundle({entryPoint: path.join(studio, 'src/index.ts'), publicDir: spec.assets,
  outDir: path.join(outDir, '.bundle')});
const browser = await openBrowser('chrome', {browserExecutable: spec.browser});
try {
  const composition = await selectComposition({serveUrl: bundlePath, id: spec.composition,
    inputProps: spec.props, puppeteerInstance: browser, logLevel: 'warn'});
  for (const frame of spec.frames) {
    const output = path.join(outDir, `frame-${String(frame).padStart(5, '0')}.jpg`);
    await renderStill({serveUrl: bundlePath, composition, inputProps: spec.props, output, frame,
      imageFormat: 'jpeg', scale: 1, puppeteerInstance: browser, logLevel: 'warn'});
    console.log(output);
  }
} finally {
  await browser.close({silent: true});
  await fs.rm(path.join(outDir, '.bundle'), {recursive: true, force: true});
}
