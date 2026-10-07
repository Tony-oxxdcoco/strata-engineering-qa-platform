"""Project-scoped page extraction and immutable corrected OCR revisions."""
from fastapi import Body, Depends
from .storage import public, digest, now
from .ocr import capabilities, recognize


def register_ocr(app,store,user,access,resource,require_fields):
    prefix='/api/v1/projects/{project_id}'
    @app.get('/api/v1/ocr')
    def config(account=Depends(user)): return capabilities()

    @app.get(prefix+'/files/{file_id}/ocr')
    def pages(project_id:str,file_id:str,account=Depends(user)):
        with store.session() as session:
            access(session,project_id,account);resource(session,project_id,'file',file_id)
            return {'items':[public(r) for r in store.list(session,project_id,'ocr') if r.data['file_id']==file_id]}

    @app.post(prefix+'/files/{file_id}/ocr')
    def extract(project_id:str,file_id:str,body:dict=Body(...),account=Depends(user)):
        require_fields(body,['page'],['page'])
        with store.session() as session:
            access(session,project_id,account,{'engineer','reviewer'})
            source=resource(session,project_id,'file',file_id)
            if not source.data['filename'].lower().endswith('.pdf'): raise ValueError('OCR supports explicit PDF pages only')
            sha=source.data['sha256'];content=store.get_blob(sha)
        result=recognize(content,body['page']);image=result.pop('image')
        with store.session.begin() as session:
            access(session,project_id,account,{'engineer','reviewer'}) # Recheck after bounded expensive operation.
            source=resource(session,project_id,'file',file_id)
            if source.data['sha256']!=sha: raise ValueError('OCR source changed')
            image_sha=store.put_blob(image)
            image_row=store.add(session,'file',project_id,{'filename':f'ocr-page-{body["page"]}-{sha[:8]}.png','sha256':image_sha,'size_bytes':len(image),'ingestion':{'status':'OCR_PAGE_IMAGE','format':'png','pages':[]},'uploaded_by':account['id'],'derived_from':file_id})
            row=store.add(session,'ocr',project_id,{**result,'file_id':file_id,'source_sha256':sha,'image_file_id':image_row.id,'image_sha256':image_sha,'extraction_hash':digest(result),'created_by':account['id'],'corrections':[]})
            store.audit(session,project_id,account['id'],'ocr.extracted',row.id,{'file_id':file_id,'page':body['page'],'state':'PENDING_REVIEW'})
            return {'ocr':public(row)}

    @app.post(prefix+'/ocr/{ocr_id}/confirm')
    def confirm(project_id:str,ocr_id:str,body:dict=Body(...),account=Depends(user)):
        require_fields(body,['text','reason','numbers_units_columns_checked'],['text','reason','numbers_units_columns_checked'])
        if not isinstance(body['text'],str) or (not body['text'].strip() or not 1<=len(body['text'])<=200_000) or not isinstance(body['reason'],str) or (not body['reason'].strip() or not 1<=len(body['reason'])<=1000) or body['numbers_units_columns_checked'] is not True: raise ValueError('Confirm corrected text, review reason, and all numbers / units / column relationships')
        with store.session.begin() as session:
            access(session,project_id,account,{'reviewer'})
            original=resource(session,project_id,'ocr',ocr_id)
            if original.data['state']!='PENDING_REVIEW': raise ValueError('OCR revision is already confirmed; extract a new page to create another revision')
            from .provenance import validate_ocr
            source,image=validate_ocr(store,session,original)
            records={**original.data,'state':'CONFIRMED','confirmed_text':body['text'],'confirmed_by':account['id'],'confirmed_at':now(),'corrections':[{'original':original.data['text'],'corrected':body['text'],'reason':body['reason'],'actor':account['id']}]}
            records['confirmation_hash']=digest({'text':body['text'],'image':original.data['image_sha256'],'source':original.data['source_sha256'],'page':original.data['page']})
            transcript=body['text'].encode('utf-8')
            transcription=store.add(session,'file',project_id,{'filename':f'confirmed-ocr-page-{records["page"]}-{source.data["sha256"][:8]}.txt','sha256':store.put_blob(transcript),'size_bytes':len(transcript),'ingestion':{'status':'NEEDS_MAPPING','format':'txt','pages':[{'page':records['page'],'text':body['text']}],'warnings':['Human-confirmed OCR transcription; engineering mapping and calculation still require review.']},'uploaded_by':account['id'],'derived_from':source.id,'ocr_id':original.id,'confirmation_hash':records['confirmation_hash'],'original_pdf_sha256':source.data['sha256'],'page_image_sha256':records['image_sha256']})
            records['transcription_file_id']=transcription.id
            store.change(session,original,records)
            # Immutable source bytes retained. Newly confirmed text requires new rule/snapshot.
            store.audit(session,project_id,account['id'],'ocr.confirmed',original.id,{'file_id':source.id,'page':records['page'],'hash':records['confirmation_hash']})
            return {'ocr':public(original)}
