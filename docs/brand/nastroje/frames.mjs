import fs from "fs";import {spawn} from "child_process";
const [,,PAGE,OUTDIR,SCHEME,FPS]=process.argv;const fps=+FPS;fs.mkdirSync(OUTDIR,{recursive:true});
const ch=spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",["--headless=new","--disable-gpu","--remote-debugging-port=9333",`--user-data-dir=${OUTDIR}/../chrome-prof`,"--allow-file-access-from-files","about:blank"],{stdio:"ignore"});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));let list;for(let i=0;i<50;i++){try{list=await (await fetch("http://127.0.0.1:9333/json")).json();if(list.find(t=>t.type==="page"))break}catch{}await sleep(200)}
const ws=new WebSocket(list.find(t=>t.type==="page").webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
let id=0;const pend={};ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&pend[m.id]){pend[m.id](m);delete pend[m.id]}};
const cmd=(method,params={})=>new Promise(r=>{const i=++id;pend[i]=r;ws.send(JSON.stringify({id:i,method,params}))});
const ev=async x=>(await cmd("Runtime.evaluate",{expression:x,awaitPromise:true,returnByValue:true})).result.result.value;
await cmd("Emulation.setDeviceMetricsOverride",{width:420,height:460,deviceScaleFactor:1,mobile:false});
await cmd("Emulation.setEmulatedMedia",{features:[{name:"prefers-color-scheme",value:SCHEME}]});
await cmd("Page.navigate",{url:"file://"+PAGE});await sleep(1500);await ev("document.fonts.ready.then(()=>1)");
const end=await ev("setup(23)");const n=Math.ceil(end*fps);
for(let i=0;i<=n;i++){await ev(`frame(${i/fps})`);const r=await cmd("Page.captureScreenshot",{format:"png"});fs.writeFileSync(`${OUTDIR}/f${String(i).padStart(4,"0")}.png`,Buffer.from(r.result.data,"base64"))}
console.log("frames",n+1);ws.close();ch.kill();
