#!/usr/bin/env python3
"""Synthetic image-only PDF; handwritten truth predates OCR or checker output."""
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont
root=Path(__file__).resolve().parents[1]
font_path='/System/Library/Fonts/Supplemental/Arial.ttf'
font=ImageFont.truetype(font_path,28);small=ImageFont.truetype(font_path,18)
im=Image.new('RGB',(1200,700),'white');d=ImageDraw.Draw(im)
d.text((50,40),'SYNTHETIC OCR SOFTWARE TEST - NOT CLIENT ENGINEERING DATA',fill='black',font=small)
for y,row in zip((120,200,280,360),[('Object','Force','Unit'),('A-01','-0.75','kN'),('A-02','1.20','N'),('A-03','100.05','kN')]):
    for x,text in zip((80,460,850),row): d.text((x,y),text,fill='black',font=font)
    d.line((50,y+60,1150,y+60),fill='black',width=2)
d.text((50,520),'Verify decimal points, minus signs, units and each row / column relationship.',fill='black',font=small)
im.save(root/'examples/scan.synthetic.pdf','PDF',resolution=120)
truth={'authority':'synthetic','independent':True,'basis':'Literal table defined by the fixture author before recognition; not checker output.','rows':[{'id':'A-01','force':-0.75,'unit':'kN'},{'id':'A-02','force':1.20,'unit':'N'},{'id':'A-03','force':100.05,'unit':'kN'}],'required_tokens':['-0.75','1.20','100.05','kN','N','A-01','A-02','A-03'],'confirmation_text':'SYNTHETIC OCR SOFTWARE TEST\nObject Force Unit\nA-01 -0.75 kN\nA-02 1.20 N\nA-03 100.05 kN'}
(root/'examples/scan.truth.synthetic.json').write_text(json.dumps(truth,indent=2)+'\n')
