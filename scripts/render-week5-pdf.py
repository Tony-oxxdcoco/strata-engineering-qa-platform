#!/usr/bin/env python3
"""Render the deliberately limited editable Week5 PPTX to a matching PDF.

This is a local subset renderer, not a PowerPoint compatibility certification.
Reject unsupported content. Source is actual PPTX XML and embedded screenshots.
Requires existing reportlab only for authoring, never application runtime.
"""
import argparse,io,json,math,posixpath,re,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
NS={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
ROOT=Path(__file__).resolve().parents[1]
font_root=Path('/System/Library/Fonts/Supplemental')
for name,file in [('Arial','Arial.ttf'),('ArialBold','Arial Bold.ttf')]:
    p=font_root/file
    if not p.exists():raise RuntimeError('Arial font required for faithful rendering: '+str(p))
    pdfmetrics.registerFont(TTFont(name,str(p)))

def wrap(value,font,size,width):
    lines=[];line=''
    for word in value.split(' '):
        candidate=line+' '+word if line else word
        if pdfmetrics.stringWidth(candidate,font,size)>width and line:lines.append(line);line=word
        else:line=candidate
    lines.append(line)
    return lines

def render(pptx,pdf):
    issues=[]
    with zipfile.ZipFile(pptx) as z:
        pres=ET.fromstring(z.read('ppt/presentation.xml'));size=pres.find('p:sldSz',NS)
        W,H=int(size.get('cx'))/12700,int(size.get('cy'))/12700
        c=canvas.Canvas(str(pdf),pagesize=(W,H));c.setTitle('STRATA COMP9900 Week 5 Demo A');c.setAuthor('STRATA team preparation')
        names=sorted((n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+.xml',n)),key=lambda n:int(re.search(r'(\d+)\.xml',n).group(1)))
        for number,name in enumerate(names,1):
            root=ET.fromstring(z.read(name));bg=root.find('p:cSld/p:bg/p:bgPr/a:solidFill/a:srgbClr',NS)
            c.setFillColor(HexColor('#'+(bg.get('val') if bg is not None else 'FFFFFF')));c.rect(0,0,W,H,fill=1,stroke=0)
            relname=posixpath.join(posixpath.dirname(name),'_rels',posixpath.basename(name)+'.rels')
            rels={v.get('Id'):posixpath.normpath(posixpath.join(posixpath.dirname(name),v.get('Target'))) for v in ET.fromstring(z.read(relname))}
            for item in root.find('p:cSld/p:spTree',NS):
                tag=item.tag.rsplit('}',1)[-1]
                if tag=='nvGrpSpPr':continue
                if tag=='grpSpPr':
                    transform=item.find('a:xfrm',NS)
                    if transform is not None and (any(v not in ('0','false') for v in transform.attrib.values()) or any(v!='0' for child in transform for v in child.attrib.values())):
                        raise ValueError('Unsupported rotation or group transformation; export edited slides using Office')
                    continue
                if tag not in ('sp','pic','cxnSp'):raise ValueError('Unsupported slide content '+tag)
                transform=item.find('p:spPr/a:xfrm',NS)
                if transform is None or any(transform.get(attr,'0') not in ('0','false') for attr in ('rot','flipH','flipV')):
                    raise ValueError('Unsupported rotation or reflection; export edited slides using Office')
                geometry=item.find('p:spPr/a:prstGeom',NS)
                expected_geometry='line' if tag=='cxnSp' else 'rect'
                if geometry is None or geometry.get('prst') != expected_geometry:
                    raise ValueError('Unsupported slide geometry; export edited slides using Office')
                off=transform.find('a:off',NS);ext=transform.find('a:ext',NS)
                x,y,w,h=[int(v)/12700 for v in [off.get('x'),off.get('y'),ext.get('cx'),ext.get('cy')]]
                if tag=='pic':
                    ref=item.find('p:blipFill/a:blip',NS).get('{'+NS['r']+'}embed')
                    c.drawImage(ImageReader(io.BytesIO(z.read(rels[ref]))),x,H-y-h,w,h,preserveAspectRatio=True,anchor='c');continue
                if tag=='cxnSp':
                    c.setStrokeColor(HexColor('#146E6A'));c.setLineWidth(1.5);c.line(x,H-y,x+w,H-y-h)
                    angle=math.atan2(-h,w);px,py=x+w,H-y-h
                    q=c.beginPath();q.moveTo(px,py);q.lineTo(px-7*math.cos(angle-.45),py-7*math.sin(angle-.45));q.lineTo(px-7*math.cos(angle+.45),py-7*math.sin(angle+.45));q.close();c.setFillColor(HexColor('#146E6A'));c.drawPath(q,fill=1,stroke=0);continue
                fill=item.find('p:spPr/a:solidFill/a:srgbClr',NS)
                if fill is not None:
                    c.setFillColor(HexColor('#'+fill.get('val')));c.setStrokeColor(HexColor('#146E6A'));c.setLineWidth(1);c.rect(x,H-y-h,w,h,fill=1,stroke=1)
                body=item.find('p:txBody',NS)
                if body is None:
                    c.setStrokeColor(HexColor('#98B2AB'));c.setLineWidth(1);c.setDash(5,4);c.rect(x,H-y-h,w,h,fill=0,stroke=1);c.setDash()
                    continue
                props=body.find('a:bodyPr',NS);center=props.get('anchor')=='ctr'
                paragraphs=body.findall('a:p',NS);rendered=[]
                for paragraph in paragraphs:
                    runs=paragraph.findall('a:r',NS)
                    if len(runs)!=1:raise ValueError('Only single-style paragraphs are supported')
                    run=runs[0];rp=run.find('a:rPr',NS);font='ArialBold' if rp.get('b')=='1' else 'Arial';fontsize=int(rp.get('sz'))/100
                    value=run.find('a:t',NS).text or ''
                    colour=rp.find('a:solidFill/a:srgbClr',NS);colour=colour.get('val') if colour is not None else '203B3E'
                    for line in wrap(value,font,fontsize,w-16 if center else w):rendered.append((line,font,fontsize,colour))
                total=sum(size*1.15 for _,_,size,_ in rendered)
                if total>h+2:issues.append({'slide':number,'shape':item.find('p:nvSpPr/p:cNvPr',NS).get('name'),'height':h,'required':total})
                cursor=H-y-(h-total)/2 if center else H-y
                for line,font,size,colour in rendered:
                    c.setFont(font,size);c.setFillColor(HexColor('#'+colour));baseline=cursor-size
                    if center:c.drawCentredString(x+w/2,baseline,line)
                    else:c.drawString(x,baseline,line)
                    cursor-=size*1.15
            c.showPage()
        c.save()
    if issues:raise ValueError(json.dumps({'text_fit_issues':issues}))
    return {'renderer':'limited PPTX XML to PDF, embedded Arial, reportlab','slides':len(names),'native_powerpoint_verified':False,'text_fit_issues':[]}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--pptx',type=Path,default=ROOT/'docs/week5/WEEK5_DEMO.pptx');parser.add_argument('--pdf',type=Path,default=ROOT/'docs/week5/WEEK5_DEMO.pdf');args=parser.parse_args()
    print(json.dumps(render(args.pptx,args.pdf),ensure_ascii=False))
