/**
 * 把 docs/assets/*.mmd 渲染为 PNG 与 SVG（供 Word/PDF 交付件使用）。
 *
 * 设计要点：
 * 1. 不依赖 @mermaid-js/mermaid-cli（它会额外下载自己的 Chromium）。改为复用
 *    本机已有的浏览器（Chrome / Edge），无头模式 + 命令行截图参数直接出图。
 * 2. **使用自包含的 UMD 构建 `dist/mermaid.min.js`，不用 ESM 构建。**
 *    原因：mermaid 12 的 ESM 构建靠 `import ... from "./chunks/..."` 加载几十个
 *    分块，内联到 HTML 后这些相对路径在 file:// 下解析不到，模块静默不加载
 *    （2026-09-13 实测踩过此坑）。UMD 构建是单文件、零相对 import，稳定可用。
 * 3. **Markdown 中的 Mermaid 源码始终是权威版本**；本脚本只产出交付用的位图，
 *    从此图有源码，不再出现"只有位图改不动"的情况。
 *
 * 用法：node render-mmd.mjs <输入.mmd> <输出前缀> [宽度px]
 *   node tools/render-mmd.mjs docs/assets/fig-architecture.mmd docs/assets/fig-architecture 2400
 *
 * 环境变量：
 *   MERMAID_DIR  含 node_modules/mermaid 的目录（默认取当前工作目录）
 *   CHROME_PATH  浏览器可执行文件路径（默认自动探测 Chrome / Edge）
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { spawn } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const [input, outPrefix, widthArg] = process.argv.slice(2);
if (!input || !outPrefix) {
  console.error('用法: node render-mmd.mjs <输入.mmd> <输出前缀> [宽度px]');
  process.exit(2);
}
const WIDTH = Number(widthArg || 2400);

function findBrowser() {
  const cands = [
    process.env.CHROME_PATH,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    join(process.env.LOCALAPPDATA || '', 'Google\\Chrome\\Application\\chrome.exe'),
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ].filter(Boolean);
  for (const c of cands) if (existsSync(c)) return c;
  return null;
}

function findMermaidUmd() {
  const roots = [process.env.MERMAID_DIR, process.cwd()].filter(Boolean);
  for (const r of roots) {
    const p = join(r, 'node_modules', 'mermaid', 'dist', 'mermaid.min.js');
    if (existsSync(p)) return p;
  }
  return null;
}

const chrome = findBrowser();
if (!chrome) {
  console.error('未找到可用浏览器。请设置 CHROME_PATH 指向 chrome.exe / msedge.exe。');
  process.exit(2);
}
const mermaidUmd = findMermaidUmd();
if (!mermaidUmd) {
  console.error('未找到 mermaid 的 UMD 构建（node_modules/mermaid/dist/mermaid.min.js）。');
  console.error('请设置 MERMAID_DIR 指向含 node_modules/mermaid 的目录。');
  process.exit(2);
}

const source = readFileSync(input, 'utf8').trim();
const mermaidCode = readFileSync(mermaidUmd, 'utf8');

const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>PENDING</title>
<style>
  html,body { margin:0; padding:0; background:#ffffff; }
  #out { display:inline-block; padding:28px; }
  #out svg { display:block; }
</style>
</head><body>
<div id="out"></div>
<script>${mermaidCode}</script>
<script>
(async function () {
  const out = document.getElementById('out');
  try {
    const M = (window.mermaid && window.mermaid.default) ? window.mermaid.default : window.mermaid;
    M.initialize({
      startOnLoad: false,
      theme: 'neutral',
      securityLevel: 'loose',
      fontFamily: '"Microsoft YaHei","PingFang SC","Noto Sans CJK SC",sans-serif',
      flowchart: {
        htmlLabels: true,
        curve: 'basis',
        nodeSpacing: Number('${process.env.MMD_NODE_SPACING || 45}'),
        rankSpacing: Number('${process.env.MMD_RANK_SPACING || 70}'),
        useMaxWidth: false
      }
    });
    const res = await M.render('figure', ${JSON.stringify(source)});
    out.innerHTML = res.svg;
    const el = out.querySelector('svg');
    if (el) {
      const vb = el.viewBox && el.viewBox.baseVal;
      if (vb && vb.width) { el.setAttribute('width', vb.width); el.setAttribute('height', vb.height); }
      el.removeAttribute('style');
      document.title = 'RENDER_OK';
    } else {
      document.title = 'RENDER_FAIL';
      out.textContent = 'NO_SVG_ELEMENT';
    }
  } catch (e) {
    document.title = 'RENDER_FAIL';
    out.textContent = 'MERMAID_ERROR: ' + (e && e.message ? e.message : String(e));
  }
})();
</script>
</body></html>`;

mkdirSync(dirname(outPrefix), { recursive: true });
const assetsDir = resolve(dirname(outPrefix));
const scratch = join(assetsDir, `.render-${process.pid}.html`);
writeFileSync(scratch, html, 'utf8');
const scratchUrl = pathToFileURL(scratch).href;

const svgOut = resolve(`${outPrefix}.svg`);
const pngOut = resolve(`${outPrefix}.png`);
const profileDir = join(assetsDir, '.chrome-profile');

function chromeRun(args) {
  return new Promise((res) => {
    const p = spawn(chrome, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '', err = '';
    p.stdout.on('data', (d) => (out += d));
    p.stderr.on('data', (d) => (err += d));
    p.on('close', (code) => res({ code, out, err }));
  });
}

const baseArgs = [
  '--headless=new',
  '--disable-gpu',
  '--no-sandbox',
  '--hide-scrollbars',
  '--disable-extensions',
  '--disable-background-networking',
  '--disable-sync',
  '--no-first-run',
  '--virtual-time-budget=15000',
  `--user-data-dir=${profileDir}`,
];

const t0 = Date.now();

// ---------- 1) dump-dom 取回渲染后的 SVG ----------
const domRes = await chromeRun([...baseArgs, '--dump-dom', scratchUrl]);
if (!domRes.out.includes('RENDER_OK')) {
  const reason = domRes.out.match(/(MERMAID_ERROR:[^<]{0,300}|NO_SVG_ELEMENT)/);
  console.error('渲染失败。');
  if (reason) console.error('  原因: ' + reason[0]);
  const lines = domRes.err.split('\n')
    .filter((l) => l.trim() && !/DevTools|Fontconfig|GPU|Vulkan|voice|registration|GCM|DEPRECATED/i.test(l));
  if (lines.length) console.error('  浏览器 stderr:\n    ' + lines.slice(0, 8).join('\n    '));
  console.error(`  DOM 长度: ${domRes.out.length} 字节（title=${(domRes.out.match(/<title>(.*?)<\/title>/) || [])[1]}）`);
  rmSync(scratch, { force: true });
  process.exit(1);
}

const svgMatch = domRes.out.match(/<svg[\s\S]*?<\/svg>/);
if (!svgMatch) {
  console.error('DOM 中标记为渲染成功，但未找到 <svg> 元素');
  rmSync(scratch, { force: true });
  process.exit(1);
}
let svgText = svgMatch[0];
if (!/\sxmlns=/.test(svgText)) {
  svgText = svgText.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"');
}
writeFileSync(svgOut, '<?xml version="1.0" encoding="UTF-8"?>\n' + svgText + '\n', 'utf8');

// ---------- 2) 由 viewBox 计算截图窗口 ----------
const vbMatch = svgText.match(/viewBox="([\d.\-\s]+)"/);
let vw = 1600, vh = 900;
if (vbMatch) {
  const p = vbMatch[1].trim().split(/\s+/).map(Number);
  if (p.length === 4 && p[2] > 0 && p[3] > 0) { vw = Math.ceil(p[2]); vh = Math.ceil(p[3]); }
}
const scale = WIDTH / vw;
const PAD = 28 * 2;
const winW = WIDTH + PAD;
const winH = Math.ceil(vh * scale) + PAD;

// ---------- 3) 截图 ----------
const shotRes = await chromeRun([
  ...baseArgs,
  `--window-size=${winW},${winH}`,
  '--force-device-scale-factor=1',
  `--screenshot=${pngOut}`,
  scratchUrl,
]);
rmSync(scratch, { force: true });
rmSync(profileDir, { recursive: true, force: true });

if (!existsSync(pngOut)) {
  console.error('截图未生成。浏览器 stderr（截断）：');
  console.error(shotRes.err.split('\n').filter((l) => l.trim() && !/DevTools|GPU|Vulkan/i.test(l)).slice(0, 10).join('\n'));
  process.exit(1);
}

console.log(JSON.stringify({
  ok: true,
  input: resolve(input),
  browser: chrome,
  mermaidUmd,
  svg: svgOut,
  png: pngOut,
  svgViewBox: `${vw}x${vh}`,
  pngWindow: `${winW}x${winH}`,
  scale: Number(scale.toFixed(3)),
  elapsedMs: Date.now() - t0,
}, null, 2));
