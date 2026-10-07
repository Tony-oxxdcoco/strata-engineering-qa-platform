"""Optional local scan OCR. Recognition is untrusted until explicit human review."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from pypdf import PdfReader
from io import BytesIO
ROOT=Path(__file__).resolve().parents[2]


def capabilities():
    provider='macos-vision' if platform.system()=='Darwin' and shutil.which('swift') else None
    return {'enabled':os.environ.get('STRATA_OCR_ENABLED')=='1','provider':provider,'renderer':bool(shutil.which('pdftoppm')),'available':bool(provider and shutil.which('pdftoppm')),'policy':'OCR is unverified; each used page needs explicit human correction and confirmation.'}


def _recognize(content,page):
    config=capabilities()
    if not config['enabled']: raise ValueError('Optional OCR is disabled; enable STRATA_OCR_ENABLED=1 or use a manually transcribed authorised source')
    if not config['available']: raise ValueError('Optional OCR requires macOS Vision / Swift and pdftoppm; this platform is not verified')
    if type(page) is not int or not 1<=page<=200: raise ValueError('Select one explicit PDF page (1–200)')
    try:
        reader=PdfReader(BytesIO(content),strict=True)
        if reader.is_encrypted or page>len(reader.pages): raise ValueError('PDF page is unavailable or encrypted')
    except Exception as error: raise ValueError('PDF cannot be rendered for OCR') from error
    with tempfile.TemporaryDirectory(prefix='strata-ocr-') as directory:
        tmp=Path(directory); source=tmp/'source.pdf';source.write_bytes(content)
        # Bounded raster size and process time. No user-controlled executable or flags.
        subprocess.run([shutil.which('pdftoppm'),'-f',str(page),'-l',str(page),'-scale-to','2000','-singlefile','-png',str(source),str(tmp/'page')],check=True,capture_output=True,timeout=15)
        image=(tmp/'page.png').read_bytes()
        if not 0<len(image)<=10_000_000: raise ValueError('OCR page image exceeds size limit')
        environment={**os.environ,'CLANG_MODULE_CACHE_PATH':str(tmp/'module-cache'),'SWIFT_MODULECACHE_PATH':str(tmp/'module-cache')}
        completed=subprocess.run([shutil.which('swift'),'-module-cache-path',str(tmp/'module-cache'),str(ROOT/'scripts/vision-ocr.swift'),str(tmp/'page.png')],capture_output=True,timeout=25,env=environment)
        if completed.returncode or len(completed.stdout)>500_000: raise ValueError('Local OCR failed or exceeded its output limit; keep the page pending correction')
        try: lines=json.loads(completed.stdout)
        except (ValueError,UnicodeError) as error: raise ValueError('Invalid OCR output') from error
        if not isinstance(lines,list) or len(lines)>5000: raise ValueError('OCR output exceeds line limit')
        from .data_tools import _json
        _json(lines)
        for line in lines:
            if not isinstance(line,dict) or set(line)!={'text','confidence','box'} or not isinstance(line['text'],str) or type(line['confidence']) not in (int,float) or not 0<=line['confidence']<=1 or not isinstance(line['box'],list) or len(line['box'])!=4 or any(type(v) not in (int,float) or not 0<=v<=1 for v in line['box']): raise ValueError('Invalid OCR line metadata')
        return {'provider':config['provider'],'page':page,'text':'\n'.join(line['text'] for line in lines),'lines':lines,'state':'PENDING_REVIEW','image':image,'warning':'Small decimals, minus signs, units and column relationships must be checked against the page image.'}


def recognize(content,page):
    try: return _recognize(content,page)
    except subprocess.TimeoutExpired as error: raise ValueError('Local OCR timeout; keep the page pending review or upload an authorised manual transcription') from error
    except (subprocess.CalledProcessError,OSError) as error: raise ValueError('Local OCR renderer or provider failed; no engineering values were inferred') from error
