from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
out=Path('store-assets');out.mkdir(exist_ok=True)
green='#10221e'; mint='#81ded2'; gold='#e6bd71'; light='#f6ead1'; coral='#f2a77b'
def emblem(draw,cx,cy,r):
    draw.ellipse((cx-r,cy-r,cx+r,cy+r),fill='#20382f',outline=gold,width=max(2,r//25))
    points=[(22,30),(34,30),(41,63),(50,39),(58,39),(67,63),(74,30),(86,30),(72,80),(62,80),(54,56),(46,80),(36,80)]
    draw.polygon([(cx+(x-54)*r/45,cy+(y-54)*r/45) for x,y in points],fill=gold)
    for x,col in [(34,mint),(74,coral)]:
        draw.polygon([(cx+(a-54)*r/45,cy+(b-54)*r/45) for a,b in [(x-7,87),(x,82),(x+7,87),(x,92)]],fill=col)
def font(size,bold=False,serif=False):
    fam='DejaVuSerif' if serif else 'DejaVuSans'
    return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/'+fam+('-Bold' if bold else '')+'.ttf',size)
im=Image.new('RGBA',(512,512),green);d=ImageDraw.Draw(im);emblem(d,256,256,211);im.save(out/'icon-512.png',optimize=True)
im=Image.new('RGB',(1024,500),green);d=ImageDraw.Draw(im)
d.rectangle((12,12,1011,487),outline='#a58551',width=2)
d.rectangle((23,23,1000,476),outline='#344339',width=1)
d.text((58,72),'OBERBERGISCHES LAND',fill=mint,font=font(19,True))
d.text((55,111),'Wiehl',fill=light,font=font(109,True,True))
d.text((62,245),'51674 · Das Stadtduell',fill=gold,font=font(34,True))
d.text((63,318),'Würfeln. Straßen kaufen.',fill=light,font=font(26))
d.text((63,357),'Zu zweit die Stadt entdecken.',fill=light,font=font(26))
emblem(d,824,250,138)
im.save(out/'feature-1024x500.png',optimize=True)
