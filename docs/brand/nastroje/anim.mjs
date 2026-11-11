import fs from "fs";
const OUT=process.argv[2],T=JSON.parse(fs.readFileSync(process.argv[3]));
const wm=(k,h,y)=>{const t=T[k],s=h/t.cap;return {d:t.d,s,w:t.w*s,y}};
const A=wm("CEE",30,30),Bt=wm("sub",12.5,52);const WW=Math.ceil(Math.max(A.w,Bt.w))+4;
const text=`<svg id="wm" width="${WW}" height="58" viewBox="0 0 ${WW} 58"><path class="i" transform="translate(${(WW-A.w)/2} ${A.y}) scale(${A.s})" d="${A.d}"/><path class="s" transform="translate(${(WW-Bt.w)/2} ${Bt.y}) scale(${Bt.s})" d="${Bt.d}"/></svg>`;
const css=`:root{--bg:#fbfbf9;--ink:#1b2830;--ink2:#56656e}@media (prefers-color-scheme:dark){:root{--bg:#17202a;--ink:#ecdfc5;--ink2:#9aa5ae}}
html,body{margin:0;height:100%;background:var(--bg)}body{display:flex;align-items:center;justify-content:center}
.i{fill:var(--ink)}.s{fill:var(--ink2)}`;
const core=fs.readFileSync(new URL("./tree-core.js",import.meta.url),"utf8");
fs.writeFileSync(OUT+"/splash.html",`<!doctype html><html lang="cs"><head><meta charset="utf-8"><title>CEE – úvodní animace</title><style>${css}
#stage{position:relative;width:min(70vmin,420px)}#gen{position:absolute;left:4px;top:-6px;font:italic 13px Charis,'Charis SIL',Georgia,serif;color:var(--ink2)}
#sv{display:block;width:100%;aspect-ratio:1}#tp{fill:var(--ink)}#wm{display:block;margin:4px auto 0;opacity:0}</style></head><body>
<div id="stage"><div id="gen">generace 0</div><svg id="sv" viewBox="0 0 32 32"><path id="tp"/></svg>${text}</div>
<script>${core}
const reduce=matchMedia("(prefers-reduced-motion: reduce)").matches;
play(document.getElementById("sv"),document.getElementById("tp"),document.getElementById("wm"),document.getElementById("gen"),{seed:23,instant:reduce,at:(q=>q==null?null:+q)(new URLSearchParams(location.search).get("t"))});
document.body.onclick=()=>play(document.getElementById("sv"),document.getElementById("tp"),document.getElementById("wm"),document.getElementById("gen"),{seed:Math.floor(Math.random()*1e6)});
</script></body></html>`);
fs.writeFileSync(OUT+"/loader.html",`<!doctype html><html lang="cs"><head><meta charset="utf-8"><title>CEE – čekání na dosimulování</title><style>${css}
.ld{display:flex;align-items:center;gap:12px;color:var(--ink);font:14px system-ui}
.ld circle{fill:var(--ink);transform-box:fill-box;transform-origin:center;animation:p 1.6s ease-in-out infinite}
@keyframes p{0%,100%{transform:scale(.35)}40%{transform:scale(1)}}
@media (prefers-reduced-motion:reduce){.ld circle{animation:none;transform:scale(.7)}}</style></head><body>
<div class="ld"><svg width="36" height="36" viewBox="0 0 32 32">${[[7,7],[16,7],[25,7],[7,16],[16,16],[25,16],[7,25],[16,25],[25,25]].map(([x,y])=>`<circle cx="${x}" cy="${y}" r="3.6" style="animation-delay:${(((x-7)/9+(25-y)/9)*0.18).toFixed(2)}s"/>`).join("")}</svg><span>Simuluji generaci <b id="g">412</b>…</span></div>
<script>let g=412;setInterval(()=>document.getElementById("g").textContent=++g,700)</script></body></html>`);
