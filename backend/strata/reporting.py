"""Human-readable printable report from verified records only."""
import html
import json


def render_report(project, run, provenance, findings, exported_at):
    def esc(value):
        return html.escape(str(value if value is not None else 'Not supplied'))

    def value(item):
        if isinstance(item, (dict, list)):
            return esc(json.dumps(item, ensure_ascii=False, separators=(', ', ': ')))
        return esc(item)

    def facts(items):
        return '<dl>' + ''.join(f'<dt>{esc(label)}</dt><dd>{value(item)}</dd>' for label, item in items) + '</dl>'

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
            label = detail.get('label') or detail.get('name') or detail.get('id') or 'Calculation detail'
            pairs = [(key.replace('_', ' ').replace('Id', ' ID').capitalize(), item) for key, item in detail.items() if key not in {'label', 'name', 'id'}]
            rows.append(f'<div class="detail"><h3>{esc(label)}</h3>{facts(pairs)}</div>')
        checks.append(f'<section><h2>{esc(result["id"])} <span class="status">{esc(result["status"])}</span></h2><p>{esc(result.get("summary", ""))}</p>{"".join(rows)}</section>')
    inputs = []
    for source in provenance:
        inputs.append(f'<article><h3>{esc(source["side"].capitalize())}: {esc(source["title"])}</h3>' + facts([
            ('Original file', source['filename']), ('Snapshot', source['snapshot_id']),
            ('Source SHA-256', source['source_sha256']), ('Input SHA-256', source['input_hash']),
            ('Authority', 'Synthetic software fixture' if source['synthetic'] else 'Supplied input; engineering authority depends on approved rules'),
            ('Mapping', source.get('mapping_note')),
        ]) + ''.join('<div class="detail"><h4>Field correction</h4>'+facts(list(c.items()))+'</div>' for c in source.get('corrections', [])) + '</article>')
    sources = []
    for citation in run.get('citations', []):
        sources.append(f'<article><h3>{esc(citation.get("rule_id"))} · {esc(citation.get("version"))}</h3><p>{esc(citation.get("title"))} — {esc(citation.get("locator"))}</p><blockquote>{esc(citation.get("quote"))}</blockquote>'+facts([('Authority', citation.get('authority')), ('Source SHA-256', citation.get('source_sha256')), ('Approved by', citation.get('approved_by'))])+'</article>')
    issue_sections = []
    for issue in findings:
        notes = ''.join(f'<p>{esc(n["at"])} · {esc(n.get("username", n["actor"]))} · {esc(n["action"])}<br>{esc(n["note"])}</p>' for n in issue.get('notes', []))
        issue_sections.append(f'<article><h3>{esc(issue["finding_id"])} · {esc(issue["state"])}</h3>'+facts([('Original technical result', issue['technical_status']), ('Original run', issue['source_run_id']), ('Resolution run', issue.get('resolution_run_id'))])+notes+'</article>')
    reviews = ''.join(f'<article><h3>{esc(r["action"])} · {esc(r.get("username",r.get("actor")))}</h3><p>{esc(r["note"])}</p><p class="subtle">{esc(r.get("created_at"))}</p></article>' for r in run.get('reviews', []))
    meta = facts([('Run', run['id']), ('Review state', run['review_state']), ('Workflow', run.get('workflow_version')), ('Rules SHA-256', run.get('rule_hash')), ('Current dependencies', 'Stale: '+ '; '.join(run['stale_reasons']) if run['stale'] else 'Current at export'), ('Exported', exported_at)])
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>STRATA QA report</title><style>
body{{font:14px Georgia,serif;line-height:1.45;max-width:900px;margin:36px auto;color:#183437}}h1{{font-size:30px;margin-bottom:4px}}h2{{font-size:19px}}h3{{font-size:15px;margin:12px 0 5px}}h4{{font-size:13px}}p{{margin:8px 0}}.subtle{{color:#56706c;font-size:12px}}.status{{font:600 13px Arial,sans-serif;padding:4px 10px;background:#e9f0e9;border-radius:3px}}.meta{{background:#eef4f1;padding:14px 18px;margin:16px 0}}dl{{display:grid;grid-template-columns:145px 1fr;gap:3px 12px;margin:8px 0;font:12px/1.5 Arial,sans-serif}}dt{{font-weight:600;color:#496260}}dd{{margin:0;overflow-wrap:anywhere}}section{{border-top:1px solid #b8cac6;margin-top:22px;padding-top:10px}}article{{padding:6px 0 12px}}.detail{{border-left:3px solid #d7e5df;padding:2px 12px;margin:10px 0}}blockquote{{margin:8px 0;padding:8px 14px;background:#f4f7f3;white-space:pre-wrap}}h2,h3{{break-after:avoid}}article,.detail{{break-inside:avoid}}footer{{border-top:1px solid #aaa;margin-top:22px;padding-top:10px;font-size:11px}}@page{{size:A4;margin:17mm;@bottom-right{{content:"Page " counter(page) " / " counter(pages);font:10px Arial,sans-serif;color:#56706c}}}}@media print{{body{{margin:0;max-width:none}}}}
</style><body><header><p class="subtle">ENGINEERING ASSURANCE · TRACEABLE REVIEW RECORD</p><h1>STRATA · QA review record</h1><p>{esc(project['name'])}</p></header><div class="meta"><strong>Technical status: {esc(run['status'])}</strong>{meta}</div><p>{esc(run.get('explanation',''))}</p>{''.join(checks)}<section><h2>Input provenance and mapping</h2>{''.join(inputs)}</section><section><h2>Finding resolution history</h2>{''.join(issue_sections) or '<p>No registered findings in this run lineage.</p>'}</section><section><h2>Source citations</h2>{''.join(sources) or '<p>No approved source citation is available.</p>'}</section><section><h2>Review history</h2>{reviews or '<p>Not confirmed by a reviewer.</p>'}</section><footer>This record covers only the selected checks and supplied sources. Synthetic fixtures are not client engineering validation. Software sign-off is not structural design certification. The JSON export preserves the machine-readable record. Use the browser print dialog to save PDF.</footer></body></html>'''
