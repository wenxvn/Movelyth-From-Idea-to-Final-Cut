"""Edge labels should describe the edge they are attached to."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.mark.skipif(not shutil.which("node") or not (ROOT / "studio/node_modules/esbuild").exists(),
                    reason="需要 Node 和 studio 依赖")
def test_stacked_edge_labels_are_between_their_nodes():
    script = r"""
const esbuild = require('esbuild');
const source = `
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {DiagramLayer} from './src/components/DiagramLayer';
const layer = {id:'route', color:'cyan', steps:[], nodes:[
  {id:'network',label:'网络',x:500,y:100},
  {id:'received',label:'收到',x:500,y:300},
  {id:'read',label:'读取',x:500,y:500}], edges:[
  {source:'network',target:'received',label:'接收'},
  {source:'received',target:'read',label:'应用读取'}]};
const theme = {text:'#fff',surfaceAlt:'#222',surface:'#111',backgroundBase:'#000',muted:'#aaa'};
console.log(renderToStaticMarkup(<DiagramLayer layer={layer as any} theme={theme as any}
  time={0} reveal={1} box={{x:0,y:0,w:500,h:800}}/>));`;
const built = esbuild.buildSync({stdin:{contents:source,resolveDir:process.cwd(),loader:'tsx'},
  bundle:true,platform:'node',format:'cjs',write:false,external:['react','react-dom/server']});
const m = {exports:{}};
new Function('require','module','exports', built.outputFiles[0].text)(require,m,m.exports);
"""
    result = subprocess.run([shutil.which("node"), "-e", script], cwd=ROOT / "studio",
                            capture_output=True, text=True, encoding="utf-8", timeout=30, check=True)
    def y_of(label):
        match = re.search(r'<text x="500" y="([\d.]+)"[^>]*>' + label + r'</text>', result.stdout)
        assert match, f"没有找到标签 {label}"
        return float(match.group(1))

    assert 156 < y_of("接收") < 244
    assert 356 < y_of("应用读取") < 444
