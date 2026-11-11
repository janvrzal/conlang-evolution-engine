import sys,glob
from PIL import Image
src,out=sys.argv[1],sys.argv[2]
fr=[Image.open(p).convert("RGB") for p in sorted(glob.glob(src+"/f*.png"))]
d=[40]*len(fr); d[0]=500; d[-1]=2500
pal=fr[-1].quantize(colors=64,method=Image.Quantize.MEDIANCUT)
q=[f.quantize(palette=pal,dither=Image.Dither.NONE) for f in fr]
q[0].save(out+".gif",save_all=True,append_images=q[1:],duration=d,loop=0,optimize=True,disposal=1)
fr[0].save(out+".webp",save_all=True,append_images=fr[1:],duration=d,loop=0,quality=90,method=6)
