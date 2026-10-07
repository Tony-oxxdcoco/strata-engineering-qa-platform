"""Verify original and derived file chains without interpreting engineering values."""
from .storage import Resource, digest


def _validate_file(store,session,row,seen=None):
    seen=set() if seen is None else seen
    if row is None or row.kind!='file' or row.id in seen or len(seen)>=10: raise ValueError('Invalid or cyclic original-source chain')
    seen.add(row.id)
    content=store.get_blob(row.data['sha256'])
    parent_id=row.data.get('derived_from')
    if parent_id:
        parent=session.get(Resource,parent_id)
        if not parent or parent.project_id!=row.project_id: raise ValueError('Original source belongs to another project or is missing')
        validate_file(store,session,parent,seen)
    if row.data.get('ocr_id'):
        ocr=session.get(Resource,row.data['ocr_id'])
        if not ocr or ocr.kind!='ocr' or ocr.project_id!=row.project_id or ocr.data.get('state')!='CONFIRMED' or ocr.data.get('transcription_file_id')!=row.id: raise ValueError('OCR transcription is not confirmed')
        validate_ocr(store,session,ocr)
        data=ocr.data
        expected=digest({'text':data['confirmed_text'],'image':data['image_sha256'],'source':data['source_sha256'],'page':data['page']})
        if expected!=data.get('confirmation_hash') or expected!=row.data.get('confirmation_hash') or content!=data['confirmed_text'].encode('utf-8') or not parent_id or data['file_id']!=parent_id or parent.data['sha256']!=data['source_sha256']: raise ValueError('OCR confirmation integrity failed')
        image=session.get(Resource,data['image_file_id'])
        if not image or image.kind!='file' or image.project_id!=row.project_id or image.data['sha256']!=data['image_sha256'] or image.data.get('derived_from')!=parent_id: raise ValueError('OCR page image binding integrity failed')
        store.get_blob(data['image_sha256'])
    return content


def _validate_ocr(store,session,row):
    if not row or row.kind!='ocr': raise ValueError('Invalid OCR record')
    data=row.data
    source=session.get(Resource,data['file_id']);image=session.get(Resource,data['image_file_id'])
    if not source or source.kind!='file' or source.project_id!=row.project_id or source.data['sha256']!=data['source_sha256'] or not image or image.kind!='file' or image.project_id!=row.project_id or image.data['sha256']!=data['image_sha256'] or image.data.get('derived_from')!=source.id: raise ValueError('OCR source or page image binding integrity failed')
    extracted={k:data[k] for k in ('provider','page','text','lines','warning')}|{'state':'PENDING_REVIEW'}
    if digest(extracted)!=data['extraction_hash']: raise ValueError('OCR extraction integrity failed')
    store.get_blob(source.data['sha256']);store.get_blob(image.data['sha256'])
    return source,image


def validate_file(store,session,row,seen=None):
    try: return _validate_file(store,session,row,seen)
    except (KeyError,TypeError,AttributeError) as error: raise ValueError('Original source metadata integrity failed') from error


def validate_ocr(store,session,row):
    try: return _validate_ocr(store,session,row)
    except (KeyError,TypeError,AttributeError) as error: raise ValueError('OCR extraction metadata integrity failed') from error
