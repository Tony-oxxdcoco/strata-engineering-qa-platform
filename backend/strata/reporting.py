"""Printable reports: translated presentation, immutable original engineering records.

Only application headings, known field labels, status values and scope notes are
translated. Source quotes, names, identifiers, engineering values/formulas and
raw notes remain exactly as recorded. JSON export is handled separately by the API.
"""
from functools import lru_cache
import html
import json
from pathlib import Path


@lru_cache(maxsize=2)
def _catalogue(language):
    if language not in ('en', 'zh-CN'):
        raise ValueError('Report language must be en or zh-CN')
    return json.loads((Path(__file__).with_name('locales') / (language + '.json')).read_text(encoding='utf-8'))


def render_report(project, run, provenance, findings, exported_at, language='en'):
    catalogue = _catalogue(language)

    def text(key):
        return catalogue.get(key, key)

    def esc(item):
        return html.escape(str(item if item is not None else text('Not supplied')))

    def translated(key):
        return esc(text(key))

    def status(item):
        return translated(item) if isinstance(item, str) else esc(item)

    def value(item):
        if isinstance(item, (dict, list)):
            # Nested records retain every original key, value and status. A
            # translated field heading does not rewrite their JSON contents.
            return esc(json.dumps(item, ensure_ascii=False, separators=(', ', ': ')))
        return esc(item)

    def facts(items, technical=False):
        rows = []
        field_labels = {
            'expected': 'Expected', 'actual': 'Actual', 'tolerance': 'Tolerance',
            'unit': 'Unit', 'status': 'Status', 'reason': 'Reason', 'formula': 'Formula',
            'location': 'Location', 'evidenceRefs': 'EvidenceRefs', 'evidence_refs': 'Evidence refs',
            'dependencies': 'Dependencies', 'source_value': 'Source value', 'target_value': 'Target value',
            'source_unit': 'Source unit', 'target_unit': 'Target unit', 'delta': 'Delta',
            'path': 'Path', 'operator': 'Operator', 'value': 'Value', 'min': 'Min', 'max': 'Max',
        }
        for key, item in items:
            if technical:
                label = field_labels.get(key, key)
                displayed = status(item) if key == 'status' else value(item)
            else:
                label = key
                displayed = status(item) if key in {'Original technical result', 'Review state'} else value(item)
            rows.append(f'<dt>{translated(label)}</dt><dd>{displayed}</dd>')
        return '<dl>' + ''.join(rows) + '</dl>'

    checks = []
    for result in run['results']:
        details = result.get('details', [])
        if not isinstance(details, list):
            details = [details]
        rows = []
        for detail in details:
            if not isinstance(detail, dict):
                rows.append(f'<p>{value(detail)}</p>')
                continue
            label = detail.get('label') or detail.get('name') or detail.get('id')
            displayed_label = esc(label) if label is not None else translated('Calculation detail')
            pairs = [(key, item) for key, item in detail.items() if key not in {'label', 'name', 'id'}]
            rows.append(f'<div class="detail"><h3>{displayed_label}</h3>{facts(pairs, technical=True)}</div>')
        checks.append(
            f'<section><h2>{esc(result["id"])} <span class="status">{status(result["status"])}</span></h2>'
            f'<p class="subtle">{translated("Original technical summary")}</p>'
            f'<p>{esc(result.get("summary", ""))}</p>{"".join(rows)}</section>'
        )
    inputs = []
    for source in provenance:
        authority = text('Synthetic software fixture') if source['synthetic'] else text('Supplied input; engineering authority depends on approved rules')
        side = translated(source['side'].capitalize())
        inputs.append(f'<article><h3>{side}: {esc(source["title"])}</h3>' + facts([
            ('Original file', source['filename']), ('Snapshot', source['snapshot_id']),
            ('Source SHA-256', source['source_sha256']), ('Input SHA-256', source['input_hash']),
            ('Authority', authority), ('Mapping', source.get('mapping_note')),
            ('Adapter', source.get('adapter_id')), ('Adapter SHA-256', source.get('adapter_hash')),
            ('Field mapping provenance', source.get('mapping_provenance', [])),
        ]) + ''.join('<div class="detail"><h4>' + translated('Field correction') + '</h4>' +
                     # Correction dictionaries are original audit records.
                     facts(list(c.items())) + '</div>' for c in source.get('corrections', [])) + '</article>')
    sources = []
    for citation in run.get('citations', []):
        sources.append(f'<article><h3>{esc(citation.get("rule_id"))} · {esc(citation.get("version"))}</h3>'
                       f'<p>{esc(citation.get("title"))} — {esc(citation.get("locator"))}</p>'
                       f'<blockquote>{esc(citation.get("quote"))}</blockquote>' + facts([
                           ('Authority', text(citation.get('authority'))),
                           ('Source SHA-256', citation.get('source_sha256')),
                           ('Approved by', citation.get('approved_by')),
                       ]) + '</article>')
    issue_sections = []
    for issue in findings:
        notes = ''.join(f'<p>{esc(n["at"])} · {esc(n.get("username", n.get("actor")))} · {esc(n["action"])}<br>{esc(n["note"])}</p>' for n in issue.get('notes', []))
        issue_sections.append(f'<article><h3>{esc(issue["finding_id"])} · {status(issue["state"])}</h3>' + facts([
            ('Original technical result', issue['technical_status']), ('Original run', issue['source_run_id']),
            ('Resolution run', issue.get('resolution_run_id')),
        ]) + notes + '</article>')
    # Actions, actors and notes in the review history are original audit content.
    reviews = ''.join(f'<article><h3>{esc(r["action"])} · {esc(r.get("username", r.get("actor")))}</h3>'
                      f'<p>{esc(r["note"])}</p><p class="subtle">{esc(r.get("created_at"))}</p></article>'
                      for r in run.get('reviews', []))
    document_state = ('DRAFT - CURRENT REVIEW REQUIRED' if run['stale'] else
                      'REVIEWED SOFTWARE RECORD' if run['review_state'] == 'APPROVED' else
                      'DRAFT - NOT REVIEWED')
    dependency_state = text('Stale: ') + '; '.join(run['stale_reasons']) if run['stale'] else text('Current at export')
    meta = facts([
        ('Run', run['id']), ('Review state', run['review_state']), ('Workflow', run.get('workflow_version')),
        ('Rules SHA-256', run.get('rule_hash')), ('Current dependencies', dependency_state), ('Exported', exported_at),
    ])
    material_requests = []
    for item in run.get('material_requests', []):
        material_requests.append('<article><h3>' + esc(item['what']) + '</h3>' + facts([
            ('Why needed', item['why']), ('Where to add', item['where']), ('Affected finding', item['finding']),
        ]) + '</article>')
    footer = 'This record covers only the selected checks and supplied sources. Synthetic fixtures are not client engineering validation. Software sign-off is not structural design certification. The JSON export preserves the machine-readable record. Use the browser print dialog to save PDF.'
    return f'''<!doctype html><html lang="{language}"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{translated('STRATA QA report')}</title><style>
body{{font:14px Georgia,serif;line-height:1.45;max-width:900px;margin:36px auto;color:#183437;padding:0 14px}}h1{{font-size:30px;margin-bottom:4px}}h2{{font-size:19px}}h3{{font-size:15px;margin:12px 0 5px}}h4{{font-size:13px}}p{{margin:8px 0;overflow-wrap:anywhere}}.subtle{{color:#56706c;font-size:12px}}.status{{font:600 13px Arial,sans-serif;padding:4px 10px;background:#e9f0e9;border-radius:3px}}.meta{{background:#eef4f1;padding:14px 18px;margin:16px 0}}dl{{display:grid;grid-template-columns:145px 1fr;gap:3px 12px;margin:8px 0;font:12px/1.5 Arial,sans-serif}}dt{{font-weight:600;color:#496260}}dd{{margin:0;overflow-wrap:anywhere}}section{{border-top:1px solid #b8cac6;margin-top:22px;padding-top:10px}}article{{padding:6px 0 12px}}.detail{{border-left:3px solid #d7e5df;padding:2px 12px;margin:10px 0}}blockquote{{margin:8px 0;padding:8px 14px;background:#f4f7f3;white-space:pre-wrap;overflow-wrap:anywhere}}h2,h3{{break-after:avoid;overflow-wrap:anywhere}}article,.detail{{break-inside:avoid}}footer{{border-top:1px solid #aaa;margin-top:22px;padding-top:10px;font-size:11px}}@page{{size:A4;margin:17mm;@bottom-right{{content:"{text('Page')} " counter(page) " / " counter(pages);font:10px Arial,sans-serif;color:#56706c}}}}@media(max-width:550px){{body{{margin:18px auto}}dl{{grid-template-columns:1fr}}dd{{margin-bottom:8px}}}}@media print{{body{{margin:0;max-width:none;padding:0}}}}
</style><body><header><p class="subtle">{translated('ENGINEERING ASSURANCE · TRACEABLE REVIEW RECORD')}</p><h1>{translated('STRATA · QA review record')}</h1><p class="document-state"><strong>{translated(document_state)}</strong></p><p>{esc(project['name'])}</p></header><div class="meta"><strong>{translated('Technical status')}: {status(run['status'])}</strong>{meta}</div><p class="subtle">{translated('Original technical explanation')}</p><p>{esc(run.get('explanation',''))}</p>{''.join(checks)}<section><h2>{translated('Material requests')}</h2>{''.join(material_requests) or '<p>' + translated('No outstanding material requests.') + '</p>'}</section><section><h2>{translated('Input provenance and mapping')}</h2>{''.join(inputs)}</section><section><h2>{translated('Finding resolution history')}</h2>{''.join(issue_sections) or '<p>' + translated('No registered findings in this run lineage.') + '</p>'}</section><section><h2>{translated('Source citations')}</h2>{''.join(sources) or '<p>' + translated('No approved source citation is available.') + '</p>'}</section><section><h2>{translated('Review history')}</h2>{reviews or '<p>' + translated('Not confirmed by a reviewer.') + '</p>'}</section><footer>{translated(footer)}</footer></body></html>'''
