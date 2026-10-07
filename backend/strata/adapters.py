"""Versioned, explicit table adapters. No inferred fields, units or expressions."""
from __future__ import annotations
import copy
import csv
import io
import json
import math
import re
from pathlib import Path
from .data_tools import UNITS, MAX_ROWS, _json, _json_float, _pointer, ingest
from .storage import canonical, digest

SCHEMA = 'strata-adapter/1'

class _NumericLiteral(str):
    """Keep a JSON floating-point lexeme until its exact location is known."""

def _normalize_json_numbers(value, filename, profile, path='', depth=0):
    if depth>32: raise MappingError([{'file':filename,'table':'*','field':path or '/', 'reason':'JSON nesting exceeds 32 levels'}])
    if isinstance(value,_NumericLiteral):
        try: return _json_float(str(value))
        except ValueError as exc:
            tables=[mapping['source'] for mapping in profile['tables'] if path.startswith(mapping['source']+'/') or path==mapping['source']]
            raise MappingError([{'file':filename,'table':max(tables,key=len) if tables else '*','field':path or '/', 'reason':str(exc)}]) from exc
    if isinstance(value,dict):
        return {key:_normalize_json_numbers(child,filename,profile,path+'/'+key.replace('~','~0').replace('/','~1'),depth+1) for key,child in value.items()}
    if isinstance(value,list):
        return [_normalize_json_numbers(child,filename,profile,path+'/'+str(index),depth+1) for index,child in enumerate(value)]
    return value

class MappingError(ValueError):
    def __init__(self, errors):
        self.errors = errors[:100]
        super().__init__('Explicit mapping failed; inspect file, table and field locations.')

def exact(obj, keys, label):
    if not isinstance(obj, dict) or set(obj) != set(keys):
        raise ValueError(f'{label}: missing or unsupported fields')

def pointer(path):
    if not isinstance(path, str) or not re.fullmatch(r'/(?:[^~/]|~[01])+(?:/(?:[^~/]|~[01])+)*', path) or len(path)>256:
        raise ValueError('Use a nonempty JSON pointer with valid ~0/~1 escapes')
    return [x.replace('~1','/').replace('~0','~') for x in path[1:].split('/')]

def put(obj, path, value):
    tokens=pointer(path)
    node=obj
    for token in tokens[:-1]:
        if token not in node: node[token]={}
        if not isinstance(node[token],dict): raise ValueError(f'Conflicting output path {path}')
        node=node[token]
    if tokens[-1] in node: raise ValueError(f'Output path already exists: {path}')
    node[tokens[-1]]=value

def names(items):
    return isinstance(items,list) and 0<len(items)<=100 and all(isinstance(x,str) and x.strip() and len(x)<=160 for x in items) and len(items)==len(set(items))

def _validate_profile(value):
    _json(value)
    exact(value, ['schema','id','version','title','authority','format','base','tables'],'Adapter')
    if value['schema']!=SCHEMA or value['format'] not in ('csv','xlsx','json') or value['authority'] not in ('synthetic','client'):
        raise ValueError('Unsupported adapter schema, format or authority')
    for key in ('id','version','title'):
        if not isinstance(value[key],str) or not value[key].strip() or len(value[key])>160: raise ValueError(f'Invalid adapter {key}')
    if not isinstance(value['base'],dict) or value['base'].get('synthetic') is not (value['authority']=='synthetic'):
        raise ValueError('base.synthetic must explicitly match adapter authority')
    if not isinstance(value['tables'],list) or not 0<len(value['tables'])<=20: raise ValueError('Adapter needs 1–20 table mappings')
    destinations=[]
    sources=[]
    for table in value['tables']:
        required_table={'source','target','mode','fields','ignored_columns'}
        if not isinstance(table,dict) or not required_table<=set(table) or set(table)-required_table-{'unique_by'}:
            raise ValueError('Table: missing or unsupported fields')
        if not isinstance(table['source'],str) or not table['source'] or len(table['source'])>256: raise ValueError('Explicit table name/path required')
        if value['format']=='csv' and table['source']!='csv': raise ValueError('CSV table source must be csv')
        if value['format']=='json': pointer(table['source'])
        pointer(table['target']); destinations.append(table['target']); sources.append(table['source'])
        if table['mode'] not in ('rows','single'): raise ValueError('Table mode must be rows or single')
        if not isinstance(table['fields'],list) or not 0<len(table['fields'])<=100: raise ValueError('Table needs 1–100 explicit fields')
        ignored=table['ignored_columns']
        if not isinstance(ignored,list) or len(ignored)>100 or (ignored and not names(ignored)): raise ValueError('Invalid ignored_columns')
        aliases=list(ignored); targets=[]
        for field in table['fields']:
            allowed={'aliases','target','type','required','unit'}
            if not isinstance(field,dict) or not {'aliases','target','type','required'}<=set(field) or set(field)-allowed: raise ValueError('Invalid field mapping')
            if not names(field['aliases']) or field['type'] not in ('number','string','boolean') or type(field['required']) is not bool: raise ValueError('Invalid aliases, type or required flag')
            pointer(field['target']); targets.append(field['target']); aliases.extend(field['aliases'])
            if 'unit' in field:
                unit=field['unit']; exact(unit,['aliases','target','output'],'Unit conversion')
                if field['type']!='number' or not names(unit['aliases']) or unit['target'] not in UNITS: raise ValueError('Only explicit supported numeric unit conversions are available')
                pointer(unit['output']); targets.append(unit['output']); aliases.extend(unit['aliases'])
        if len(aliases)!=len(set(aliases)): raise ValueError('Aliases, unit fields and ignored columns must not overlap')
        check_paths(targets)
        if 'unique_by' in table:
            if table['mode']!='rows' or not names(table['unique_by']): raise ValueError('unique_by needs explicit mapped paths on a rows table')
            field_targets={field['target'] for field in table['fields']}
            if not set(table['unique_by'])<=field_targets: raise ValueError('unique_by must reference explicitly mapped fields')
            for path in table['unique_by']: pointer(path)
    if len(sources)!=len(set(sources)): raise ValueError('Map each source table once')
    check_paths(destinations)
    base=copy.deepcopy(value['base'])
    for dest in destinations: put(base,dest,[])
    return copy.deepcopy(value)

def check_paths(paths):
    if any(a==b or a.startswith(b+'/') or b.startswith(a+'/') for i,a in enumerate(paths) for b in paths[i+1:]): raise ValueError('Output paths overlap')

def source_tables(filename, content, profile):
    expected='.'+profile['format']
    if Path(filename).suffix.lower()!=expected: raise ValueError(f'{filename}: adapter expects {expected}')
    if len(content)>10_000_000: raise ValueError('Source exceeds 10 MB')
    if expected=='.xlsx':
        result=ingest(filename,content)
        tables={}
        for table in result['tables']:
            rows=[]
            for row in table['rows']:
                cells={c['column']:c for c in row['cells']}
                rows.append((row['row'],{k:c.get('value') for k,c in cells.items()},cells))
            tables[table['name']]=(table['columns'],rows)
        return tables
    text=content.decode('utf-8-sig')
    if expected=='.csv':
        if len(content)>1_048_576: raise ValueError(f'{filename}: CSV exceeds 1 MiB')
        data=list(csv.reader(io.StringIO(text),strict=True))
        if not data or not data[0] or any(not x.strip() for x in data[0]) or len(set(data[0]))!=len(data[0]) or len(data[0])>100: raise ValueError(f'{filename}: missing, duplicate or oversized headers')
        if len(data)>MAX_ROWS+1: raise ValueError(f'{filename}: too many rows')
        rows=[]
        for index,row in enumerate(data[1:],2):
            # Ignore physically empty rows only. A partially populated row is
            # validated normally, and original line numbers remain unchanged.
            if not row or all(value=='' for value in row): continue
            if len(row)!=len(data[0]): raise MappingError([{'file':filename,'table':'csv','row':index,'field':'*','reason':'Row width does not match header'}])
            rows.append((index,dict(zip(data[0],row)),{}))
        return {'csv':(data[0],rows)}
    def pairs(items):
        obj={}
        for key,value in items:
            if key in obj: raise ValueError(f'{filename}: duplicate JSON key {key}')
            obj[key]=value
        return obj
    raw=json.loads(text,object_pairs_hook=pairs,parse_float=_NumericLiteral,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON constant')))
    raw=_normalize_json_numbers(raw,filename,profile)
    _json(raw)
    tables={}
    for mapping in profile['tables']:
        records=_pointer(raw,mapping['source'])
        single=isinstance(records,dict)
        if single: records=[records]
        if not isinstance(records,list) or len(records)>MAX_ROWS or any(not isinstance(row,dict) for row in records): raise ValueError(f'{filename}: {mapping["source"]} must be an object or bounded object list')
        columns=sorted({key for row in records for key in row})
        tables[mapping['source']]=(columns,[(i,row,{key:{'json_pointer':mapping['source']+('' if single else '/'+str(i))+'/'+key.replace('~','~0').replace('/','~1')} for key in row}) for i,row in enumerate(records)])
    return tables

def number(value):
    if isinstance(value,str):
        if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',value): raise ValueError('Expected an explicit decimal number')
        raw=value; value=float(value)
        if value==0 and any(c in '123456789' for c in raw.split('e')[0].split('E')[0]): raise ValueError('Numeric underflow')
    if type(value) not in (int,float) or not math.isfinite(value): raise ValueError('Expected a finite number; booleans are not numbers')
    return value

def apply_profile(filename, content, value):
    profile=validate_profile(value)
    try: tables=source_tables(filename,content,profile)
    except MappingError: raise
    except (ValueError,KeyError,UnicodeError,csv.Error,RecursionError) as error: raise MappingError([{'file':filename,'table':'*','field':'*','reason':str(error)}]) from error
    result=copy.deepcopy(profile['base']); errors=[]; provenance=[]
    for table in profile['tables']:
        name=table['source']
        def error(reason,row=None,field='*'):
            errors.append({'file':filename,'table':name,'row':row,'field':field,'reason':reason})
        if name not in tables: error('Required source table missing'); continue
        columns,rows=tables[name]
        if len(rows)==0 or (table['mode']=='single' and len(rows)!=1): error('Expected exactly one row' if table['mode']=='single' else 'Required table has no rows'); continue
        known=set(table['ignored_columns'])
        for field in table['fields']:
            known.update(field['aliases']); known.update(field.get('unit',{}).get('aliases',[]))
        for column in columns:
            if column not in known: error('Unknown column: map explicitly or list in ignored_columns',field=column)
        output=[]; identities={}
        for row_number,row,cells in rows:
            mapped={}
            for field in table['fields']:
                present=[alias for alias in field['aliases'] if alias in row]
                if len(present)!=1:
                    if len(present)>1 or field['required']: error('Ambiguous aliases' if present else 'Required field missing',row_number,field['target'])
                    continue
                column=present[0]; original=row[column]
                if original is None or original=='':
                    if field['required']: error('Required value missing',row_number,column)
                    continue
                try:
                    if cells.get(column,{}).get('type') in ('formula','error'): raise ValueError('Formula/error cells are not executed')
                    if field['type']=='number': converted=number(original)
                    elif field['type']=='boolean':
                        if type(original) is bool: converted=original
                        elif original in ('true','false'): converted=original=='true'
                        else: raise ValueError('Boolean must be true/false, not 0/1 or inferred text')
                    else:
                        if not isinstance(original,str) or len(original)>2000: raise ValueError('Expected a bounded string; no coercion inferred')
                        converted=original
                    unit=field.get('unit'); original_unit=None
                    if unit:
                        matches=[key for key in unit['aliases'] if key in row]
                        if len(matches)!=1: raise ValueError('Required unit field missing or ambiguous')
                        unitcol=matches[0]; original_unit=row[unitcol]
                        if cells.get(unitcol,{}).get('type') in ('formula','error') or not isinstance(original_unit,str) or original_unit not in UNITS: raise ValueError('Unknown unit; no conversion inferred')
                        if UNITS[original_unit][0]!=UNITS[unit['target']][0]: raise ValueError('Incompatible unit dimensions')
                        before=converted; converted*=UNITS[original_unit][1]/UNITS[unit['target']][1]
                        if not math.isfinite(converted) or before!=0 and converted==0: raise ValueError('Unit conversion overflow/underflow')
                        put(mapped,unit['output'],unit['target'])
                    put(mapped,field['target'],converted)
                    target=table['target']+(f'/{len(output)}' if table['mode']=='rows' else '')+field['target']
                    location={'file':filename,'table':name,'row':row_number,'column':column,'cell':cells.get(column,{}).get('coordinate')}
                    if cells.get(column,{}).get('json_pointer'): location['json_pointer']=cells[column]['json_pointer']
                    provenance.append({'target':target,'original_value':original,'original_unit':original_unit,'value':converted,'unit':unit['target'] if unit else None,'location':location,'adapter':{'id':profile['id'],'version':profile['version'],'sha256':digest(profile)}})
                except (ValueError,OverflowError,TypeError) as exc: error(str(exc),row_number,column)
            output.append(mapped)
            if table.get('unique_by'):
                try:
                    values=[_pointer(mapped,path) for path in table['unique_by']]
                    identity=tuple(('number' if type(item) in (int,float) else type(item).__name__,item) for item in values)
                except ValueError:
                    error('Identity field is missing; duplicate records cannot be checked',row_number,', '.join(table['unique_by']))
                else:
                    if identity in identities:
                        error(f'Duplicate explicit identity; first occurrence at row {identities[identity]}; records were not merged',row_number,', '.join(table['unique_by']))
                    else: identities[identity]=row_number
        put(result,table['target'],output[0] if table['mode']=='single' else output)
    if errors: raise MappingError(errors)
    canonical(result)
    return {'input':result,'provenance':provenance,'adapter_sha256':digest(profile)}


def validate_profile(value):
    try:
        return _validate_profile(value)
    except (TypeError, KeyError, AttributeError, OverflowError) as error:
        raise ValueError("Malformed validate_profile configuration; use the documented types") from error
