// CEE animace stavů. Stejná pravidla jako úvodní animace: každý snímek = jeden vyplněný <path>, žádná průhlednost.
const ST=(()=>{
const B=(x0,y0,x1,y1,w0,w1)=>({x0,y0,x1,y1,w0,w1,k:1});
const seed=()=>[B(1.5,14,5,14,4.4,4.2),B(5,14,12,6.5,4.2,3.8),B(12,6.5,23,6.5,3.8,3.0),B(5,14,12,21.25,4.2,3.8),B(12,21.25,18,16,3.8,3.4),B(18,16,20.5,16,3.4,3.0),B(12,21.25,18,26.5,3.8,3.4),B(18,26.5,26,26.5,3.4,2.8)];
const TIPS=[[23,6.5,3.0],[20.5,16,3.0],[26,26.5,2.8]];
const VB=[13.75-0.6-14.5,16.3-14.5,29];
function bez(s,t){const m=(s.x0+s.x1)/2,u=1-t;return[u*u*u*s.x0+3*u*u*t*m+3*u*t*t*m+t*t*t*s.x1,u*u*u*s.y0+3*u*u*t*s.y0+3*u*t*t*s.y1+t*t*t*s.y1,3*u*u*(m-s.x0)+3*t*t*(s.x1-m),6*u*t*(s.y1-s.y0)]}
function outline(s,p=1,mf){const N=s.y0===s.y1?2:32,L=[],R=[];for(let i=0;i<=N;i++){const t=p*i/N;let[x,y,dx,dy]=bez(s,t);const n=Math.hypot(dx,dy)||1;dx/=n;dy/=n;
const w=(s.w0+(s.w1*s.k-s.w0)*t)*(mf?mf(x):1)/2;L.push([x-dy*w,y+dx*w]);R.push([x+dy*w,y-dx*w])}
return "M"+L.concat(R.reverse()).map(q=>q[0].toFixed(3)+" "+q[1].toFixed(3)).join("L")+"Z"}
function rng(s){return()=>{s=s+0x6D2B79F5|0;let t=Math.imul(s^s>>>15,1|s);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function build(sd){const R=rng(sd),N=[];const tips=TIPS.map(([x,y,w])=>({x1:x,y1:y,w1:w,end:0.8,d:0}));
function grow(par,a,c,md){const d=par.d+1;if(d>md)return;const k=(c-a)<10?1:(c-a)<20?2:(R()<0.55?2:3),part=(c-a)/k;
for(let i=0;i<k;i++){const ext=d>1&&R()<0.24,len=[0,13,11,9][d]*(0.7+R()*0.6)*(ext?0.5:1);
const n=B(par.x1,par.y1,par.x1+len,a+part*(i+.5)+(R()-.5)*part*.35,par.w1,par.w1*0.7);n.d=d;n.ext=ext;n.start=par.end+0.05+R()*0.35;n.dur=0.45+R()*0.5;n.end=n.start+n.dur;N.push(n);if(!ext)grow(n,a+part*i,a+part*(i+1),md)}}
const ys=tips.map(t=>t.y1);tips.forEach((tp,i)=>{const a=i?(ys[i-1]+tp.y1)/2:tp.y1-34,c=i<2?(tp.y1+ys[i+1])/2:tp.y1+34;grow(tp,a,c,(c-a)>30?3:2)});return N}
const cl=t=>Math.max(0,Math.min(1,t)),eo=t=>1-Math.pow(1-t,3),io=t=>t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2;
function box(N){let x0=1.5,y0=4.4,x1=26,y1=28.2;N.forEach(n=>{x0=Math.min(x0,n.x1);x1=Math.max(x1,n.x1+2);y0=Math.min(y0,n.y1-2);y1=Math.max(y1,n.y1+2)});const s=Math.max(x1-x0,y1-y0)+10;return[(x0+x1)/2-0.6-s/2,(y0+y1)/2-s/2,s]}
// 1) Dosimulováno: hotový strom, stromem projde vlna od kořene k listům
function done(t,sd=23){const N=build(sd);N.forEach(n=>{if(n.ext)n.k=0.25});const X1=Math.max(...N.map(n=>n.x1));
 const mf=x=>{const q=cl((t-(x-1.5)/(X1-1.5)*0.9)/0.5);return 1+0.35*Math.sin(Math.PI*q)};
 return{d:seed().map(s=>outline(s,1,mf)).join("")+N.map(n=>outline(n,1,mf)).join(""),vb:box(N),text:cl((t-1.0)/0.4)}}
// 2) Chyba / přerušený běh: spodní větev uschne – zúží se a skloní
function wither(t){const S=seed(),e=io(cl(t/1.2));const a=S[7],b=S[6],w=3.4*(1-0.45*e);b.w1=w;a.w0=w;a.w1=2.8*(1-0.88*e);a.y1=26.5+2.2*e;a.x1=26-0.8*e;
 return{d:S.map(s=>outline(s)).join(""),vb:VB,text:cl((t-0.9)/0.4)}}
// 3) Prázdný projekt: semínko (značka) se jemně nadechuje, konce větví se pomalu natahují
function idle(t){const S=seed(),b=Math.sin(2*Math.PI*t/4);[[2,0],[5,1.3],[7,2.6]].forEach(([i,ph])=>{S[i].x1+=0.7*Math.sin(2*Math.PI*(t+ph)/4)});
 const sc=1+0.03*b,c=[13.75,16.3];return{d:S.map(s=>outline(s)).join(""),vb:[c[0]-0.6-VB[2]/2/sc,c[1]-VB[2]/2/sc,VB[2]/sc],text:1}}
// 4) Ikona v Docku: strom podle postupu simulace p ∈ <0,1>, pevný záběr
function progress(p,sd=23){const N=build(sd),Tend=Math.max(...N.map(n=>n.end)),t=0.8+p*(Tend-0.8);let d=seed().map(s=>outline(s)).join("");
 N.forEach(n=>{const q=eo(cl((t-n.start)/n.dur));if(q>0)d+=outline(n,q)});return{d,vb:box(N)}}
return{done,wither,idle,progress};})();
