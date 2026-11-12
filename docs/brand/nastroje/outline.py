import json, sys
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from pathlib import Path
F=str(Path(__file__).resolve().parents[3]/"desktop"/"static"/"fonts")+"/"
def run(font, text, track):
    f=TTFont(F+font); gs=f.getGlyphSet(); cmap=f.getBestCmap(); upm=f["head"].unitsPerEm
    os2=f["OS/2"]; x=0; pen=SVGPathPen(gs)
    for ch in text:
        g=cmap[ord(ch)]
        gs[g].draw(TransformPen(pen,(1,0,0,-1,x,0)))
        x+=gs[g].width+track
    return {"d":pen.getCommands(),"w":x-track,"upm":upm,"cap":os2.sCapHeight,"xh":os2.sxHeight}
out={"CEE":run("Charis-Regular.woff2","CEE",120),
     "sub":run("Charis-Italic.woff2","Conlang Evolution Engine",10),
     "dmg_cs":run("Charis-Regular.woff2","Přetáhni CEE do složky Aplikace",0),
     "dmg_en":run("Charis-Italic.woff2","Drag CEE to the Applications folder",0),
     "ver":run("Charis-Regular.woff2","verze 0.1.0",0)}
json.dump(out,open(sys.argv[1],"w"))
print({k:(v["w"],v["upm"],v["cap"],v["xh"]) for k,v in out.items()})
