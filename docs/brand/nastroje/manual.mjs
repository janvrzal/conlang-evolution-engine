import fs from "fs";
const O=process.argv[2],OUT=process.argv[3];
const md=fs.readFileSync(O+"/cee-mark-currentColor.svg","utf8");
const d=md.match(/ d="([^"]+)"/)[1], vb=md.match(/viewBox="([^"]+)"/)[1];
const [vx,vy,vs]=vb.split(" ").map(Number);
const mk=(cls="",extra="",inner="")=>`<svg class="mk ${cls}" viewBox="${vb}" aria-hidden="true"${extra}><path d="${d}" fill="currentColor"/>${inner}</svg>`;
const inl=f=>fs.readFileSync(O+"/"+f,"utf8").replace(/<svg /,'<svg class="fill" ');
// ochranná zóna: x = tloušťka kmene (4,4 jednotky), zóna = 1x
const x=4.4,bx0=1.5,by0=4.6,bw=24.5,bh=23.6;
const zone=`<svg class="zone" viewBox="${bx0-x-2} ${by0-x-2} ${bw+2*x+4} ${bh+2*x+4}" aria-hidden="true"><rect x="${bx0-x}" y="${by0-x}" width="${bw+2*x}" height="${bh+2*x}" fill="var(--zone)" /><rect x="${bx0}" y="${by0}" width="${bw}" height="${bh}" fill="var(--bg)"/><path d="${d}" fill="var(--ink)"/><rect x="${bx0-x}" y="${by0-x}" width="${bw+2*x}" height="${bh+2*x}" fill="none" stroke="var(--accent)" stroke-width="0.25" stroke-dasharray="0.8 0.6"/><path d="M${bx0-x} ${by0-x/2}H${bx0}" stroke="var(--accent)" stroke-width="0.3"/><text x="${bx0-x/2}" y="${by0-x/2-0.8}" text-anchor="middle" class="zx">x</text></svg>`;
const dots=`<circle cx="23" cy="6.5" r="2.6" fill="currentColor"/><circle cx="20.5" cy="16" r="2.4" fill="currentColor"/><circle cx="26" cy="26.5" r="2.8" fill="currentColor"/>`;
const bad=[
 ["Nenatahovat ani nedeformovat",mk("",' style="transform:scaleX(1.45)"')],
 ["Neotáčet",mk("",' style="transform:rotate(90deg)"')],
 ["Nepřidávat kolečka ani jiné ozdoby",mk("","",dots)],
 ["Nebarvit mimo paletu",`<svg class="mk" viewBox="${vb}" aria-hidden="true"><defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#c4508a"/><stop offset="1" stop-color="#2a6fc9"/></linearGradient></defs><path d="${d}" fill="url(#g)"/></svg>`],
 ["Nekreslit jako obrys",`<svg class="mk" viewBox="${vb}" aria-hidden="true"><path d="${d}" fill="none" stroke="currentColor" stroke-width="0.6"/></svg>`],
 ["Nepřidávat stíny ani průhlednost",mk("",' style="filter:drop-shadow(1.5px 2px 1.5px rgba(0,0,0,.45));opacity:.55"')],
 ["Nesestavovat z oddělených tahů (švy)",`<svg class="mk" viewBox="${vb}" aria-hidden="true"><path d="${d}" fill="currentColor"/><path d="M12 4V9M18 13V19M12 18.5V24" stroke="var(--bg)" stroke-width="0.35"/></svg>`],
 ["Nedávat na neklidné pozadí",`<div class="busy">${mk()}</div>`]];
const html=`<title>Značka CEE</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Charis+SIL:ital,wght@0,400;0,700;1,400&family=Piazzolla:ital,opsz,wght@0,8..30,400;0,8..30,600;1,8..30,400&family=IBM+Plex+Mono:wght@400&display=swap">
<style>
/* Rozvržení: úzký sloupec manuálu, každá kapitola = pravidlo + ukázka; barvy a písmo z Poloostrova */
:root{--bg:#fbfbf9;--panel:#eef1f2;--ink:#1b2830;--ink2:#56656e;--ink3:#8a96a0;--rule:#d1d9dc;--accent:#ae2a1f;--zone:#f3dcd8;--dark:#17202a;--paper:#ecdfc5;
--f-display:'Charis SIL','Charis CEE',Georgia,serif;--f-body:'Piazzolla',Georgia,serif;--f-mono:'IBM Plex Mono',ui-monospace,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#111a22;--panel:#17202a;--ink:#ecdfc5;--ink2:#9aa5ae;--ink3:#8a96a0;--rule:#26323d;--accent:#e8806f;--zone:#3a2622;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#111a22;--panel:#17202a;--ink:#ecdfc5;--ink2:#9aa5ae;--ink3:#8a96a0;--rule:#26323d;--accent:#e8806f;--zone:#3a2622;color-scheme:dark}
body{background:var(--bg);color:var(--ink);font:17px/1.6 var(--f-body);padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:48px 80px}
main{max-width:860px;margin:0 auto;display:grid;gap:64px}
h1,h2,h3{font-family:var(--f-display);font-weight:400;text-wrap:balance;margin:0}
h1{font-size:clamp(40px,7vw,64px);letter-spacing:.06em;line-height:1}
h2{font-size:28px;border-top:1px solid var(--rule);padding-top:20px}
h3{font-size:18px;font-style:italic;color:var(--ink2)}
p{margin:0;max-width:62ch}.lead{font-size:19px;color:var(--ink2)}
section{display:grid;gap:18px}
.hero{display:grid;grid-template-columns:auto 1fr;gap:28px;align-items:center}
.hero .mk{width:clamp(96px,18vw,148px);color:var(--ink)}
.sub{font:italic 18px var(--f-display);color:var(--ink2);margin-top:8px}
.mk{display:block;overflow:visible}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px}
.tile{background:var(--panel);border-radius:12px;padding:20px;display:grid;gap:10px;justify-items:start;min-width:0}
.tile .mk{width:72px;color:var(--ink)}
.cap{font-size:14px;color:var(--ink2)}
code,.hex{font:14px var(--f-mono)}
.zone{width:min(100%,320px);display:block}.zx{font:italic 2.2px var(--f-display);fill:var(--accent)}
.sizes{display:flex;gap:24px;align-items:flex-end;flex-wrap:wrap}.sizes div{display:grid;gap:6px;justify-items:center}
.sizes .mk{color:var(--ink)}
.sw{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}@media (max-width:560px){.sw{grid-template-columns:repeat(2,minmax(0,1fr))}}
.chip{border-radius:10px;overflow:hidden;border:1px solid var(--rule)}.chip i{display:block;height:64px}.chip div{padding:10px 12px;display:grid;gap:2px}
.chip b{font-weight:600;font-size:15px}
.modes{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
.mode{border-radius:12px;padding:28px;display:flex;gap:16px;align-items:center}.mode .mk{width:56px}
.mode.l{background:#fbfbf9;color:#1b2830;border:1px solid #d1d9dc}.mode.d{background:#17202a;color:#ecdfc5}
.lock{display:grid;gap:16px}.lock .fill{max-width:100%;height:auto;display:block}
.lockbox{border-radius:12px;padding:24px;overflow-x:auto}.lockbox.l{background:#fbfbf9;border:1px solid #d1d9dc}.lockbox.d{background:#17202a}
.bad{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px}
.bad figure{margin:0;background:var(--panel);border-radius:12px;padding:20px;display:grid;gap:12px;position:relative}
.bad .mk{width:64px;height:64px;color:var(--ink);margin:4px auto}
.bad figcaption{font-size:14px;color:var(--ink2);display:flex;gap:8px;align-items:baseline}
.bad figcaption::before{content:"×";color:var(--accent);font:700 18px var(--f-display)}
.busy{background:repeating-linear-gradient(45deg,var(--ink3) 0 6px,var(--panel) 6px 12px);border-radius:8px;padding:6px;width:max-content;margin:0 auto}.busy .mk{margin:0}
ul{margin:0;padding-left:1.2em;display:grid;gap:6px;max-width:62ch}
table{border-collapse:collapse;width:100%;font-size:15px}td,th{text-align:left;padding:8px 10px;border-bottom:1px solid var(--rule);vertical-align:top}th{font-weight:600;color:var(--ink2);font-size:14px}
.tw{overflow-x:auto}
.anim{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
.ld{display:flex;align-items:center;gap:12px}.ld circle{fill:var(--ink);transform-box:fill-box;transform-origin:center;animation:p 1.6s ease-in-out infinite}
@keyframes p{0%,100%{transform:scale(.35)}40%{transform:scale(1)}}
@media (prefers-reduced-motion:reduce){.ld circle{animation:none;transform:scale(.7)}}
@media (max-width:520px){.hero{grid-template-columns:1fr}}
</style>
<main>
<header class="hero">${mk()}<div><h1>CEE</h1><div class="sub">Conlang Evolution Engine · manuál značky</div></div></header>

<section><h2>Co značka znamená</h2>
<p class="lead">Značka je rodokmen jazyků, který se zároveň čte jako písmeno E. Z kořene vlevo se jazyk rozdělí na dvě větve, spodní se později dělí znovu. Každé rameno je jinak dlouhé a každý přechod je křivka S, stejná jako průběh jazykové změny v čase.</p>
<p>Celá značka je jeden souvislý vyplněný tvar. Větve se plynule zužují a nová větev začíná přesně tak silná, jak končí ta, ze které vyrůstá. Proto nemá švy ani schody a funguje v jedné barvě.</p></section>

<section><h2>Ochranná zóna a minimální velikost</h2>
<div class="hero" style="grid-template-columns:minmax(0,320px) 1fr">${zone}<div style="display:grid;gap:12px">
<p>Kolem značky nechej volné místo aspoň <b>x</b>, kde x je tloušťka kmene (asi 18 % šířky značky). Do zóny nesmí zasahovat text, okraje ani jiné prvky.</p>
<p>V nápisu je mezera mezi značkou a slovem CEE stejná: 1,5 x.</p></div></div>
<div class="sizes">${[96,48,32,24,16].map(s=>`<div>${mk("",` width="${s}" height="${s}"`)}<span class="cap">${s} px</span></div>`).join("")}</div>
<p>Nejmenší velikost je <b>16 px</b> (favicon). Pod 24 px se značka zobrazuje bez nápisu. Na ikonách aplikace pro 16 a 32 px se používá zvláštní verze s menším okrajem dlaždice, aby značka nebyla drobná.</p></section>

<section><h2>Barvy</h2>
<p>Barvy jsou převzaté z design systému Poloostrov. Značka má vždy jednu barvu: inkoust na pevnině, nebo papír na tmavém podkladu.</p>
<div class="sw">${[["Inkoust","#1b2830","značka a nápis na světlém podkladu"],["Pevnina","#fbfbf9","světlý podklad"],["Papír","#ecdfc5","značka na tmavém podkladu"],["Noc","#17202a","tmavý podklad"],["Břidlice","#56656e","podtitul, popisky"],["Mlha","#c3ccd0","doprovodný strom, šipky"]].map(([n,h,u])=>`<div class="chip"><i style="background:${h}"></i><div><b>${n}</b><span class="hex">${h}</span><span class="cap">${u}</span></div></div>`).join("")}</div>
<p>Červená Poloostrova (<span class="hex">#ae2a1f</span>) do značky nepatří. Zůstává pro varování a chyby v aplikaci.</p></section>

<section><h2>Písmo</h2>
<p>Nápis je sázený písmem <b>Charis</b> (SIL, licence OFL), které aplikace už používá pro IPA. „CEE“ je v regulárním řezu s prostrkáním 0,08 em, „Conlang Evolution Engine“ v kurzívě. V souborech značky je text převedený na křivky, takže nevyžaduje nainstalované písmo.</p>
<p>Texty kolem značky (instalátory, README) používají Charis, v rozhraní aplikace dál platí Piazzolla z Poloostrova.</p></section>

<section><h2>Nápis se značkou</h2>
<div class="lock"><div class="lockbox l">${inl("cee-lockup-light.svg")}</div><div class="lockbox d">${inl("cee-lockup-dark.svg")}</div></div>
<p>Vodorovný nápis je hlavní podoba pro README, web a instalátory. Samotné „CEE“ bez značky použij jen tam, kde je značka už vidět jinde, třeba v záhlaví okna vedle ikony.</p></section>

<section><h2>Světlá a tmavá verze</h2>
<div class="modes"><div class="mode l">${mk()}<div><b>Světlá</b><br><span style="font-size:15px">výchozí; ikona aplikace, dokumenty, instalátory</span></div></div><div class="mode d">${mk()}<div><b>Tmavá</b><br><span style="font-size:15px">tmavý režim aplikace, README a favicon v tmavém prohlížeči</span></div></div></div>
<ul><li>Verzi vybírej podle podkladu, ne podle vkusu: na světlém inkoust, na tmavém papír.</li><li>Favicon a README se přepínají samy (<code>prefers-color-scheme</code>, <code>&lt;picture&gt;</code>).</li><li>Ikona aplikace pro macOS má jen světlou dlaždici; ve Windows je značka vždy na světlé dlaždici, aby nezmizela na tmavém hlavním panelu.</li></ul></section>

<section><h2>Pohyb</h2>
<div class="anim"><div class="tile"><h3>Úvodní animace</h3><p class="cap">Značka se nadechne, vyroste do rodokmenu, kamera se oddálí, část větví vymře, stromem projde vlna a objeví se nápis. Trvá asi 4,5 s.</p></div>
<div class="tile"><h3>Čekání na dosimulování</h3><div class="ld"><svg width="36" height="36" viewBox="0 0 32 32">${[[7,7],[16,7],[25,7],[7,16],[16,16],[25,16],[7,25],[16,25],[25,25]].map(([a,b])=>`<circle cx="${a}" cy="${b}" r="3.6" style="animation-delay:${(((a-7)/9+(25-b)/9)*0.18).toFixed(2)}s"/>`).join("")}</svg><span>Simuluji generaci 412…</span></div></div></div>
<ul><li>Strom je v každém snímku jeden vyplněný tvar. Žádné skládání z oddělených tahů a žádná průhlednost, jinak vzniknou bílé švy.</li><li>Vymírání se ukazuje zúžením větve, ne vyblednutím.</li><li>S vypnutými animacemi (<code>prefers-reduced-motion</code>) se ukáže rovnou konečný stav.</li></ul></section>

<section><h2>Chybná použití</h2><div class="bad">${bad.map(([t,s])=>`<figure>${s}<figcaption>${t}</figcaption></figure>`).join("")}</div></section>

<section><h2>Soubory</h2><div class="tw"><table><tr><th>Soubor</th><th>K čemu</th></tr>
${[["cee-mark-currentColor.svg","značka v UI; přebírá barvu textu"],["cee-mark-ink.svg / -paper.svg","značka pro světlý / tmavý podklad"],["cee-lockup-light.svg / -dark.svg","nápis se značkou"],["favicon.svg","favicon, sám se přepíná"],["icon-macos-*.svg, icon-windows.svg","zdroje ikon aplikace"],["document.svg","ikona souboru projektu (až bude přípona .cee)"],["readme-header-*.svg, social-preview.png","GitHub"],["splash.html, loader.html","animace a jejich referenční kód"]].map(([a,b])=>`<tr><td><code>${a}</code></td><td>${b}</td></tr>`).join("")}</table></div></section>
</main>`;
fs.writeFileSync(OUT,html);
