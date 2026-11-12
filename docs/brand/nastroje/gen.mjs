import fs from "fs";
const OUT=process.argv[2], T=JSON.parse(fs.readFileSync(process.argv[3]));
const L={bg:"#fbfbf9",ink:"#1b2830",ink2:"#56656e",tree:"#c3ccd0",bd:"#d1d9dc"},D={bg:"#17202a",ink:"#ecdfc5",ink2:"#9aa5ae",tree:"#3b4955",bd:"#26323d"};
const B=(x0,y0,x1,y1,w0,w1)=>({x0,y0,x1,y1,w0,w1,k:1});
const SEED=[B(1.5,14,5,14,4.4,4.2),B(5,14,12,6.5,4.2,3.8),B(12,6.5,23,6.5,3.8,3.0),B(5,14,12,21.25,4.2,3.8),B(12,21.25,18,16,3.8,3.4),B(18,16,20.5,16,3.4,3.0),B(12,21.25,18,26.5,3.8,3.4),B(18,26.5,26,26.5,3.4,2.8)];
const TIPS=[[23,6.5,3.0],[20.5,16,3.0],[26,26.5,2.8]];
const f3=v=>(+v.toFixed(3)).toString();
function bez(s,t){const m=(s.x0+s.x1)/2,u=1-t;return[u*u*u*s.x0+3*u*u*t*m+3*u*t*t*m+t*t*t*s.x1,u*u*u*s.y0+3*u*u*t*s.y0+3*u*t*t*s.y1+t*t*t*s.y1,3*u*u*(m-s.x0)+3*t*t*(s.x1-m),6*u*t*(s.y1-s.y0)]}
const PTS=[];
function outline(s,p=1,ext=0){const N=s.y0===s.y1?2:48,Lp=[],R=[];for(let i=0;i<=N;i++){const t=p*i/N;let[x,y,dx,dy]=bez(s,t);const n=Math.hypot(dx,dy)||1;dx/=n;dy/=n;if(i===0&&ext){x-=dx*ext;y-=dy*ext}
const w=(s.w0+(s.w1*s.k-s.w0)*t)/2;Lp.push([x-dy*w,y+dx*w]);R.push([x+dy*w,y-dx*w])}
const P=Lp.concat(R.reverse());PTS.push(...P);return "M"+P.map(q=>f3(q[0])+" "+f3(q[1])).join("L")+"Z"}
function bbox(fn){PTS.length=0;const d=fn();let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;PTS.forEach(([x,y])=>{x0=Math.min(x0,x);x1=Math.max(x1,x);y0=Math.min(y0,y);y1=Math.max(y1,y)});return{d,x0,y0,x1,y1,w:x1-x0,h:y1-y0}}
const M=bbox(()=>SEED.map(s=>outline(s)).join(""));
const OPT=-0.6; // optický posun: těžší levá strana
const cx=(M.x0+M.x1)/2+OPT, cy=(M.y0+M.y1)/2;
// strom (finální stav animace, seed 23)
function rng(s){return()=>{s=s+0x6D2B79F5|0;let t=Math.imul(s^s>>>15,1|s);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function build(seed){const R=rng(seed),N=[];const tips=TIPS.map(([x,y,w])=>({x1:x,y1:y,w1:w,end:0.8,d:0}));
function grow(par,a,c,md){const d=par.d+1;if(d>md)return;const k=(c-a)<10?1:(c-a)<20?2:(R()<0.55?2:3),part=(c-a)/k;
for(let i=0;i<k;i++){const ext=d>1&&R()<0.24,len=[0,13,11,9][d]*(0.7+R()*0.6)*(ext?0.5:1);
const n=B(par.x1,par.y1,par.x1+len,a+part*(i+.5)+(R()-.5)*part*.35,par.w1,par.w1*0.7);n.d=d;n.ext=ext;n.start=par.end+0.05+R()*0.35;n.dur=0.45+R()*0.5;n.end=n.start+n.dur;N.push(n);if(!ext)grow(n,a+part*i,a+part*(i+1),md)}}
const ys=tips.map(t=>t.y1);tips.forEach((tp,i)=>{const a=i?(ys[i-1]+tp.y1)/2:tp.y1-34,c=i<2?(tp.y1+ys[i+1])/2:tp.y1+34;grow(tp,a,c,(c-a)>30?3:2)});return N}
const TREE=build(23);TREE.forEach(n=>{if(n.ext)n.k=0.25});
const TR=bbox(()=>TREE.map(n=>outline(n,1,n.d===1?0.8:0)).join(""));
const ALL={x0:Math.min(M.x0,TR.x0),y0:Math.min(M.y0,TR.y0),x1:Math.max(M.x1,TR.x1),y1:Math.max(M.y1,TR.y1)};
// text
const tx=(k,x,y,h,fill,useCap=true)=>{const t=T[k],s=h/(useCap?t.cap:t.upm);return{g:`<path transform="translate(${f3(x)} ${f3(y)}) scale(${s.toFixed(6)})" d="${t.d}" fill="${fill}"/>`,w:t.w*s}};
const svg=(w,h,inner,vb)=>`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="${vb||`0 0 ${w} ${h}`}">${inner}</svg>\n`;
const W=(n,s)=>fs.writeFileSync(OUT+"/"+n,s);
const place=(size,ox,oy,fill)=>{const sc=size/Math.max(M.w,M.h);return `<path transform="translate(${f3(ox)} ${f3(oy)}) scale(${f3(sc)}) translate(${f3(-cx)} ${f3(-cy)})" d="${M.d}" fill="${fill}"/>`};
// 1 značka
const pad=1.5,side=Math.max(M.w,M.h)+2*pad,vb=`${f3(cx-side/2)} ${f3(cy-side/2)} ${f3(side)} ${f3(side)}`;
for(const [n,c] of [["ink","#1b2830"],["paper","#ecdfc5"],["black","#000000"],["white","#ffffff"],["currentColor","currentColor"]])W(`cee-mark-${n}.svg`,svg(256,256,`<path d="${M.d}" fill="${c}"/>`,vb));
// 2 favicon (sám se přepne v tmavém režimu)
const fs0=Math.max(M.w,M.h)+0.6;W("favicon.svg",svg(32,32,`<style>path{fill:#1b2830}@media (prefers-color-scheme:dark){path{fill:#ecdfc5}}</style><path d="${M.d}"/>`,`${f3(cx-fs0/2)} ${f3(cy-fs0/2)} ${f3(fs0)} ${f3(fs0)}`));
// 3 ikony aplikace
for(const [n,c] of [["light",L],["dark",D]]){
 W(`icon-macos-${n}.svg`,svg(1024,1024,`<rect x="100" y="100" width="824" height="824" rx="185" fill="${c.bg}"/><rect x="101" y="101" width="822" height="822" rx="184" fill="none" stroke="${c.bd}" stroke-width="2"/>${place(470,512,512,c.ink)}`));
 W(`icon-square-${n}.svg`,svg(1024,1024,`<rect width="1024" height="1024" fill="${c.bg}"/>${place(600,512,512,c.ink)}`));
}
W("icon-windows.svg",svg(1024,1024,`<rect x="40" y="40" width="944" height="944" rx="190" fill="${L.bg}"/><rect x="41.5" y="41.5" width="941" height="941" rx="188.5" fill="none" stroke="${L.bd}" stroke-width="3"/>${place(600,512,512,L.ink)}`));
W("icon-macos-small.svg",svg(1024,1024,`<rect x="48" y="48" width="928" height="928" rx="210" fill="${L.bg}"/><rect x="50" y="50" width="924" height="924" rx="208" fill="none" stroke="${L.bd}" stroke-width="4"/>${place(660,512,512,L.ink)}`));
W("icon-transparent.svg",svg(1024,1024,place(880,512,512,"#1b2830")));
// 4 lockup a nápis
for(const [n,c] of [["light",L],["dark",D]]){
 const H=120,mk=place(H,H/2,H/2,c.ink),capH=H*0.46,x0=H+34,a=tx("CEE",x0,H*0.5+capH*0.42,capH,c.ink),b=tx("sub",x0+2,H*0.5+capH*0.42+44,capH*0.42,c.ink2);
 const w=Math.ceil(Math.max(x0+a.w,x0+2+b.w)+4),hh=Math.ceil(Math.max(H,H*0.5+capH*0.42+44+capH*0.42*0.45)+4);W(`cee-lockup-${n}.svg`,svg(w,hh,mk+a.g+b.g,`0 0 ${w} ${hh}`));
 const a2=tx("CEE",0,140,140,c.ink);W(`cee-wordmark-${n}.svg`,svg(Math.ceil(a2.w),150,a2.g));
}
// dokument (ikona souboru projektu)
{const c=L,x0=196,y0=100,w=632,h=824,f=168;const pg=`M${x0} ${y0+24}Q${x0} ${y0} ${x0+24} ${y0}H${x0+w-f}L${x0+w} ${y0+f}V${y0+h-24}Q${x0+w} ${y0+h} ${x0+w-24} ${y0+h}H${x0+24}Q${x0} ${y0+h} ${x0} ${y0+h-24}Z`;
 const fold=`M${x0+w-f} ${y0}V${y0+f-20}Q${x0+w-f} ${y0+f} ${x0+w-f+20} ${y0+f}H${x0+w}Z`;const a=tx("CEE",0,0,64,c.ink2);
 W("document.svg",svg(1024,1024,`<path d="${pg}" fill="${c.bg}" stroke="${c.bd}" stroke-width="6"/><path d="${fold}" fill="#e6ebed" stroke="${c.bd}" stroke-width="6" stroke-linejoin="round"/>${place(380,512,470,c.ink)}`+tx("CEE",512-a.w/2,800,64,c.ink2).g));}
// 5 hlavička README a náhled pro sdílení
function banner(c,BW,BH,n){const th=BH*0.84,sc=th/(ALL.y1-ALL.y0),ox=BW*0.07-ALL.x0*sc,oy=(BH-th)/2-ALL.y0*sc;
 const g=`<g transform="translate(${f3(ox)} ${f3(oy)}) scale(${f3(sc)})"><path d="${TR.d}" fill="${c.tree}"/><path d="${M.d}" fill="${c.ink}"/></g>`;
 const tx0=ox+ALL.x1*sc+BW*0.05,room=BW*0.93-tx0,capH=Math.min(BH*0.2,room/(T.sub.w/T.sub.cap*0.36+0.02)),a=tx("CEE",tx0,BH/2+capH*0.25,capH,c.ink),b=tx("sub",tx0+3,BH/2+capH*0.25+capH*0.95,capH*0.36,c.ink2);
 W(n,svg(BW,BH,`<rect width="${BW}" height="${BH}" fill="${c.bg}"/>`+g+a.g+b.g))}
banner(L,1280,320,"readme-header-light.svg");banner(D,1280,320,"readme-header-dark.svg");banner(L,1280,640,"social-preview.svg");
// 6 data pro animaci
W("mark-data.json",JSON.stringify({seed:SEED,tips:TIPS,center:[cx,cy],size:side}));
console.log("mark bbox",M.x0.toFixed(2),M.y0.toFixed(2),M.w.toFixed(2),M.h.toFixed(2),"tree",ALL);
// ===== grafika k vydání =====
{const c=L,WHITE="#ffffff";
 const center=(k,cx,y,h,fill)=>{const a=tx(k,0,0,h,fill);return tx(k,cx-a.w/2,y,h,fill).g};
 const tree=(bx,by,bw,bh)=>{const sc=Math.min(bw/(ALL.x1-ALL.x0),bh/(ALL.y1-ALL.y0)),ox=bx+(bw-(ALL.x1-ALL.x0)*sc)/2-ALL.x0*sc,oy=by+(bh-(ALL.y1-ALL.y0)*sc)/2-ALL.y0*sc;
  return `<g transform="translate(${f3(ox)} ${f3(oy)}) scale(${f3(sc)})"><path d="${TR.d}" fill="${c.tree}"/><path d="${M.d}" fill="#a3afb5"/></g>`};
 // DMG 660×400 (pozice ikon: aplikace 180,190 · Aplikace 480,190)
 const arrow=B(262,196,398,184,8,0.4);PTS.length=0;const ad=outline(arrow);
 const dmg=`<rect width="660" height="400" fill="${c.bg}"/>${place(30,290,52,c.ink)}${tx("CEE",314,52+11*0.42*2.2,22,c.ink).g}<path d="${ad}" fill="#b3bec3"/>${center("dmg_cs",330,322,13,c.ink)}${center("dmg_en",330,346,10.5,c.ink2)}`;
 W("dmg-background.svg",svg(660,400,dmg));
 // NSIS boční panel 164×314
 const side=(x0)=>`<rect x="${x0}" width="164" height="314" fill="${c.bg}"/>${place(40,x0+82,46,c.ink)}${center("CEE",x0+82,96,15,c.ink)}${center("ver",x0+82,116,8.5,c.ink2)}${tree(x0+14,132,136,168)}`;
 W("nsis-sidebar.svg",svg(164,314,side(0)));
 // NSIS hlavička 150×57 (bílá)
 {const a=tx("CEE",0,0,12,c.ink);W("nsis-header.svg",svg(150,57,`<rect width="150" height="57" fill="${WHITE}"/>${place(30,124,28.5,c.ink)}${tx("CEE",104-a.w,28.5+6,12,c.ink).g}`));}
 // WiX banner 493×58 (bílý, text instalátoru je vlevo)
 {const a=tx("CEE",0,0,13,c.ink);W("wix-banner.svg",svg(493,58,`<rect width="493" height="58" fill="${WHITE}"/>${place(34,462,29,c.ink)}${tx("CEE",440-a.w,29+6.5,13,c.ink).g}`));}
 // WiX dialog 493×312 (vlevo panel, vpravo bílá plocha pro text)
 W("wix-dialog.svg",svg(493,312,`<rect width="493" height="312" fill="${WHITE}"/>${side(0).replace('height="314"','height="312"')}`));
}
