import pytest
from strata.corrections import apply_corrections
from test_api import system, run


def change(path='/mass/self_weight', original=False, value=True):
    return {'path': path, 'original': original, 'value': value, 'source_locator': 'Settings / Mass / row 3', 'reason': 'Transcription correction confirmed against source'}


def test_scalar_correction_keeps_original_and_strict_types():
    original={'mass': {'self_weight': False}, 'synthetic': True}
    assert apply_corrections(original, [change()])['mass']['self_weight'] is True
    assert original['mass']['self_weight'] is False
    with pytest.raises(ValueError, match='no longer matches'):
        apply_corrections(original, [change(original=0)])


@pytest.mark.parametrize('path', ['/mass/missing','/mass/~7','/synthetic','/list/-1'])
def test_bad_or_protected_paths_rejected(path):
    with pytest.raises(ValueError):
        apply_corrections({'mass':{},'list':[False],'synthetic':False}, [change(path)])


def test_correction_api_new_identity_and_review_invalidation(system):
    _, client, base, _, seed = system
    before = seed['snapshots'][0]
    original = run(system)
    # A scalar from the actual saved input, without coupling to a checker formula.
    path='/project/name'
    previous=before['input']['project']['name']
    response=client.post(base+'/snapshots/'+before['id']+'/corrections', json={'corrections':[change(path, previous, 'Corrected project label')]})
    assert response.status_code==200, response.text
    after=response.json()['snapshot']
    assert after['id']!=before['id'] and after['parent_id']==before['id']
    assert after['file_id']==before['file_id']
    assert after['input']['project']['name']=='Corrected project label'
    assert after['corrections'][0]['confirmed_by']
    assert after['corrections'][0]['confirmed_at']
    records=client.get(base+'/dashboard').json()['snapshots']
    assert next(s for s in records if s['id']==before['id'])['input']['project']['name']==previous
    assert client.get(base+'/runs/'+original['id']).json()['run']['stale'] is True
