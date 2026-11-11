// CEE úvodní animace: celý strom je JEDEN vyplněný <path> (bez švů), přepočítaný v každém snímku.
const B=(x0,y0,x1,y1,w0,w1)=>({x0,y0,x1,y1,w0,w1,k:1});
const SEED=[B(1.5,14,5,14,4.4,4.2),B(5,14,12,6.5,4.2,3.8),B(12,6.5,23,6.5,3.8,3.0),B(5,14,12,21.25,4.2,3.8),B(12,21.25,18,16,3.8,3.4),B(18,16,20.5,16,3.4,3.0),B(12,21.25,18,26.5,3.8,3.4),B(18,26.5,26,26.5,3.4,2.8)];
const TIPS=[[23,6.5,3.0],[20.5,16,3.0],[26,26.5,2.8]];
const VB=[13.75-0.6-14.5,16.3-14.5,29];
function bez(s,t){const m=(s.x0+s.x1)/2,u=1-t;return[u*u*u*s.x0+3*u*u*t*m+3*u*t*t*m+t*t*t*s.x1,u*u*u*s.y0+3*u*u*t*s.y0+3*u*t*t*s.y1+t*t*t*s.y1,3*u*u*(m-s.x0)+3*t*t*(s.x1-m),6*u*t*(s.y1-s.y0)]}
function outline(s,p,mf){const N=s.y0===s.y1?2:32,Lp=[],R=[];for(let i=0;i<=N;i++){const t=p*i/N;let[x,y,dx,dy]=bez(s,t);const n=Math.hypot(dx,dy)||1;dx/=n;dy/=n;
const w=(s.w0+(s.w1*s.k-s.w0)*t)*(mf?mf(x):1)/2;Lp.push([x-dy*w,y+dx*w]);R.push([x+dy*w,y-dx*w])}
return "M"+Lp.concat(R.reverse()).map(q=>q[0].toFixed(3)+" "+q[1].toFixed(3)).join("L")+"Z"}
function rng(s){return()=>{s=s+0x6D2B79F5|0;let t=Math.imul(s^s>>>15,1|s);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function build(seed){const R=rng(seed),N=[];const tips=TIPS.map(([x,y,w])=>({x1:x,y1:y,w1:w,end:0.8,d:0}));
function grow(par,a,c,md){const d=par.d+1;if(d>md)return;const k=(c-a)<10?1:(c-a)<20?2:(R()<0.55?2:3),part=(c-a)/k;
for(let i=0;i<k;i++){const ext=d>1&&R()<0.24,len=[0,13,11,9][d]*(0.7+R()*0.6)*(ext?0.5:1);
const n=B(par.x1,par.y1,par.x1+len,a+part*(i+.5)+(R()-.5)*part*.35,par.w1,par.w1*0.7);n.d=d;n.ext=ext;n.start=par.end+0.05+R()*0.35;n.dur=0.45+R()*0.5;n.end=n.start+n.dur;N.push(n);if(!ext)grow(n,a+part*i,a+part*(i+1),md)}}
const ys=tips.map(t=>t.y1);tips.forEach((tp,i)=>{const a=i?(ys[i-1]+tp.y1)/2:tp.y1-34,c=i<2?(tp.y1+ys[i+1])/2:tp.y1+34;grow(tp,a,c,(c-a)>30?3:2)});return N}
const cl=t=>Math.max(0,Math.min(1,t)),eo=t=>1-Math.pow(1-t,3);let raf;
function play(sv,tp,wm,gen,o){cancelAnimationFrame(raf);const N=build(o.seed);const Tend=Math.max(...N.map(n=>n.end)),tw=Tend+0.2,X0=1.5,X1=Math.max(...N.map(n=>n.x1));
let cam=[...VB],last=performance.now();if(o.at!=null)o.instant=true;const t0=last-(o.at!=null?o.at*1000:o.instant?(tw+3)*1000:0);
function f(now){const t=(now-t0)/1000,dt=o.instant?1:Math.min(0.05,(now-last)/1000);last=now;
const mf=x=>{const q=cl((t-tw-(x-X0)/(X1-X0)*0.9)/0.55);return 1+0.32*Math.sin(Math.PI*q)};
let d=SEED.map(s=>outline(s,1,mf)).join(""),bx0=1.5,by0=4.4,bx1=26,by1=28.2;
N.forEach(n=>{const p=eo(cl((t-n.start)/n.dur));if(p<=0)return;n.k=n.ext?1-0.75*eo(cl((t-n.end-0.3)/0.5)):1;d+=outline(n,p,mf);const x=n.x1,y=n.y1;bx0=Math.min(bx0,x);bx1=Math.max(bx1,x+2);by0=Math.min(by0,y-2);by1=Math.max(by1,y+2)});
tp.setAttribute("d",d);const breath=1-0.06*Math.sin(Math.PI*cl(t/0.8));
const sz=Math.max(VB[2],bx1-bx0+12,by1-by0+12)*breath,tx=(bx0+bx1)/2-0.6-sz/2,ty=(by0+by1)/2-sz/2,k=o.instant?1:1-Math.exp(-dt*3.2);
cam=[cam[0]+(tx-cam[0])*k,cam[1]+(ty-cam[1])*k,cam[2]+(sz-cam[2])*k];sv.setAttribute("viewBox",cam.join(" ")+" "+cam[2]);
gen.textContent="generace "+Math.round(412*eo(cl((t-0.8)/(Tend-0.8))));const w=cl((t-tw-1.1)/0.6);wm.style.opacity=w;gen.style.opacity=1-w;
if(!o.manual&&!o.instant&&t<tw+2.6)raf=requestAnimationFrame(f)}
if(o.manual)return{f,t0,end:tw+2.6};raf=requestAnimationFrame(f)}
