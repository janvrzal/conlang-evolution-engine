// Snímek obrazovky aplikace v headless Chrome přes DevTools protokol + chyby z konzole.
//   node scripts/shot.mjs URL VÝSTUP.png [šířka=1440] [výška=900] [čekat_ms=4000]   (DARK=1 = tmavý režim)
// Příklad: node scripts/shot.mjs "http://127.0.0.1:1420/atlas?fixture=talvera" /tmp/atlas.png
import { spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const [url, out, w = '1440', h = '900', wait = '4000'] = process.argv.slice(2);
const CHROME = process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const port = 9300 + Math.floor(Math.random() * 500);
const chrome = spawn(CHROME, ['--headless=new', '--disable-gpu', `--remote-debugging-port=${port}`, `--user-data-dir=${mkdtempSync(join(tmpdir(), 'cee-shot-'))}`, `--window-size=${w},${h}`, '--hide-scrollbars', 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let target;
for (let i = 0; i < 50 && !target; i++) {
	await sleep(200);
	try {
		target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === 'page');
	} catch {}
}
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r, { once: true }));
let id = 0;
const pending = new Map();
const logs = [];
ws.addEventListener('message', (e) => {
	const msg = JSON.parse(e.data);
	if (msg.id && pending.has(msg.id)) pending.get(msg.id)(msg.result), pending.delete(msg.id);
	if (msg.method === 'Runtime.exceptionThrown') logs.push('EXCEPTION ' + (msg.params.exceptionDetails.exception?.description ?? msg.params.exceptionDetails.text));
	if (msg.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(msg.params.type)) logs.push(msg.params.type.toUpperCase() + ' ' + msg.params.args.map((a) => a.value ?? a.description).join(' '));
});
const send = (method, params = {}) => new Promise((r) => { const n = ++id; pending.set(n, r); ws.send(JSON.stringify({ id: n, method, params })); });
await send('Runtime.enable');
await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', { width: +w, height: +h, deviceScaleFactor: 1, mobile: false });
// DARK=1: tmavé schéma systému (prefers-color-scheme: dark)
if (process.env.DARK) await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'dark' }] });
await send('Page.navigate', { url });
await sleep(+wait);
const shot = await Promise.race([send('Page.captureScreenshot', { format: 'png' }), sleep(+(process.env.SHOT_TIMEOUT ?? 15000)).then(() => null)]);
if (shot) writeFileSync(out, Buffer.from(shot.data, 'base64'));
else console.log('TIMEOUT: stránka neodpověděla (zaseklý skript?)');
for (const l of logs) console.log(l.slice(0, 400));
console.log('ok', out);
ws.close();
chrome.kill();
process.exit(0);
