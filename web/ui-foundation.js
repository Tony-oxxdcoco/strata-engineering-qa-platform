import {t, displayStatus, getLanguage, translateMarked} from './i18n.js';

// Local, fixed SVG paths only. No icon request or third-party script is needed.
const paths = Object.freeze({
  layers:'<path d="m3 7 9-5 9 5-9 5-9-5Zm0 5 9 5 9-5M3 17l9 5 9-5"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  book:'<path d="M12 5C8 2 4 3 2 4v16c3-1 6-1 10 1 4-2 7-2 10-1V4c-3-1-7-2-10 1Zm0 0v16"/>',
  check:'<circle cx="12" cy="12" r="9"/><path d="m7 12 3 3 7-7"/>',
  cross:'<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6m0-6-6 6"/>',
  warning:'<path d="m12 3 10 18H2L12 3Zm0 6v5m0 3v.1"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  history:'<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7m2-5v6l4 2"/>',
  arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
  upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/>',
  download:'<path d="M12 3v13m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  file:'<path d="M14 2H5v20h14V7Zm0 0v5h5M8 12h8M8 16h6"/>',
  play:'<path d="m8 4 12 8-12 8Z"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  close:'<path d="m6 6 12 12M18 6 6 18"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
  refresh:'<path d="M20 8a8 8 0 0 0-14-2L3 9m0-5v5h5M4 16a8 8 0 0 0 14 2l3-3m0 5v-5h-5"/>',
  logout:'<path d="M9 4H4v16h5m6-13 5 5-5 5m-6-5h11"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
  search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
  menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
  users:'<circle cx="9" cy="8" r="3"/><path d="M3 20v-3a6 6 0 0 1 12 0v3m1-15a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 4v2"/>',
  eye:'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  chevronUp:'<path d="m6 15 6-6 6 6"/>',
  chevronDown:'<path d="m6 9 6 6 6-6"/>',
  sort:'<path d="m8 9 4-4 4 4m-8 6 4 4 4-4"/>',
  previous:'<path d="m15 6-6 6 6 6"/>',
  next:'<path d="m9 6 6 6-6 6"/>',
});
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function uiIcon(name, {size=20, className=''}={}) {
  const width=Number.isFinite(size) ? Math.max(8,Math.min(128,size)) : 20;
  return `<svg class="ui-icon ${escape(className)}" viewBox="0 0 24 24" width="${width}" height="${width}" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${paths[name] || paths.info}</svg>`;
}
const statusGroups = Object.freeze({
  success:['PASS','APPROVED','CONFIRMED','RESOLVED','VALID','READY','COMPLETED','FOUND','OK'],
  danger:['FAIL','ERROR','INVALID','BLOCKED'],
  warning:['NOT VERIFIED','STALE','CONFLICT','MISSING','NEEDS_MAPPING','NEEDS_OCR','NEEDS_REVIEW','AWAITING_EVIDENCE','EVIDENCE_REQUESTED'],
  progress:['RUNNING','QUEUED','WAITING','CANCELLING','PENDING','PENDING_REVIEW'],
  neutral:['DRAFT','UNREVIEWED','NOT REVIEWED','NOT CONFIRMED','OPEN','ASSIGNED','RETIRED','CANCELLED','STORED','CHANGED','UNCHANGED'],
});
export function statusPresentation(value) {
  const raw=String(value ?? 'UNKNOWN');
  const normalized=raw.toUpperCase();
  const tone=Object.keys(statusGroups).find(group=>statusGroups[group].includes(normalized)) || 'neutral';
  const icon=tone==='success'?'check':tone==='danger'?'cross':tone==='warning'?'warning':tone==='progress'?'clock':normalized==='DRAFT'||normalized==='UNREVIEWED'?'eye':'info';
  return {raw,tone,icon};
}
export function statusBadge(value, text=value) {
  const status=statusPresentation(value);
  const caption=String(text ?? value ?? 'UNKNOWN');
  // The translation marker belongs to the text, not the wrapper: in-place
  // translation must never delete the status icon or change protocol values.
  return `<span class="badge ui-status ui-status--${status.tone} ${escape(status.raw.toLowerCase().replace(/[^a-z0-9]+/g,'-'))}" data-status="${escape(status.raw)}">${uiIcon(status.icon,{size:15})}<span data-i18n-status="${escape(caption)}">${escape(displayStatus(caption))}</span></span>`;
}

// Numeric ordering is exact for finite decimal/scientific text. Converting a
// large integer or tiny decimal to Number would quietly merge distinct values.
function decimal(value) {
  const match=String(value).trim().match(/^([+-]?)(?:(\d+)(?:\.(\d*))?|\.(\d+))(?:[eE]([+-]?\d+))?$/);
  if(!match)return null;
  const exponent=Number(match[5] || 0);
  if(!Number.isSafeInteger(exponent) || Math.abs(exponent)>100000)return null;
  const fraction=match[3] ?? match[4] ?? '';
  const digits=((match[2] || '')+fraction).replace(/^0+/,'');
  if(!digits)return {sign:0,digits:'0',order:0};
  return {sign:match[1]==='-'?-1:1,digits,order:digits.length+exponent-fraction.length};
}
export function compareDecimalText(left,right) {
  const a=decimal(left),b=decimal(right);
  if(!a || !b)return null;
  if(a.sign!==b.sign)return a.sign-b.sign;
  if(a.sign===0)return 0;
  if(a.order!==b.order)return (a.order<b.order?-1:1)*a.sign;
  const length=Math.max(a.digits.length,b.digits.length);
  const aa=a.digits.padEnd(length,'0'),bb=b.digits.padEnd(length,'0');
  return (aa===bb?0:aa<bb?-1:1)*a.sign;
}
const searchText=(value,locale)=>String(value ?? '').normalize('NFKC').toLocaleLowerCase(locale);
const cellValue=(row,column)=>String(row[column] ?? '');
export function tableView(rows, {filter='',sortColumn=null,sortDirection='none',page=1,pageSize=10,columnTypes=[],searchRows=rows,locale=getLanguage()}={}) {
  if(!Array.isArray(rows) || rows.some(row=>!Array.isArray(row)))throw new TypeError('Table rows must be arrays of cell values.');
  if(!Array.isArray(searchRows)||searchRows.length!==rows.length||searchRows.some(row=>!Array.isArray(row)))throw new TypeError('Table search rows must match the source row count.');
  if(!Number.isInteger(pageSize)||pageSize<1||pageSize>500)throw new RangeError('Table page size must be between 1 and 500.');
  if(!Number.isInteger(page)||page<1)throw new RangeError('Table page must be a positive integer.');
  if(!['none','ascending','descending'].includes(sortDirection))throw new TypeError('Unsupported table sort direction.');
  if(sortColumn!==null&&(!Number.isInteger(sortColumn)||sortColumn<0))throw new RangeError('Table sort column must be a non-negative integer.');
  const terms=searchText(filter,locale).trim().split(/\s+/).filter(Boolean);
  const indexes=rows.map((_,index)=>index).filter(index=>{
    const haystack=searchText(searchRows[index].join(' '),locale);
    return terms.every(term=>haystack.includes(term));
  });
  if(sortColumn!==null&&sortDirection!=='none'){
    const type=columnTypes[sortColumn] || 'auto';
    const numeric=type==='number'||(type==='auto'&&rows.some(row=>cellValue(row,sortColumn).trim())&&rows.every(row=>!cellValue(row,sortColumn).trim()||decimal(cellValue(row,sortColumn))));
    const collator=new Intl.Collator(locale,{sensitivity:'base',numeric:false});
    const direction=sortDirection==='descending'?-1:1;
    indexes.sort((left,right)=>{
      const a=cellValue(rows[left],sortColumn),b=cellValue(rows[right],sortColumn);
      const aMissing=!a.trim()||(numeric&&!decimal(a));
      const bMissing=!b.trim()||(numeric&&!decimal(b));
      // Empty or invalid numbers stay last in both directions. Equal values
      // keep their original DOM order, including when descending.
      if(aMissing!==bMissing)return aMissing?1:-1;
      const comparison=aMissing?0:numeric?compareDecimalText(a,b):collator.compare(a,b);
      return comparison*direction || left-right;
    });
  }
  const pages=Math.max(1,Math.ceil(indexes.length/pageSize));
  const currentPage=Math.min(page,pages),offset=(currentPage-1)*pageSize;
  const visible=indexes.slice(offset,offset+pageSize);
  return {rowIndexes:visible,allIndexes:indexes,total:rows.length,filtered:indexes.length,page:currentPage,pages,start:visible.length?offset+1:0,end:offset+visible.length};
}

// Restorable state contains presentation preferences only, never rows, source
// values, IDs or permission data. The application owns project/view scoping.
export function validatedTableState(snapshot,{columnCount=null,sortableColumns=null}={}) {
  if(!snapshot || typeof snapshot!=='object' || Array.isArray(snapshot))throw new TypeError('Table state must be an object.');
  const state={filter:snapshot.filter ?? '',sortColumn:snapshot.sortColumn ?? null,sortDirection:snapshot.sortDirection ?? 'none',page:snapshot.page ?? 1,pageSize:snapshot.pageSize ?? 10};
  if(typeof state.filter!=='string')throw new TypeError('Table filter must be text.');
  tableView([],{...state});
  if(state.sortColumn!==null && ((columnCount!==null && state.sortColumn>=columnCount)||(sortableColumns!==null&&!sortableColumns.includes(state.sortColumn))))throw new RangeError('Unsupported table sort column.');
  return state;
}

const controllers=new WeakMap();
function localLabel(doc,key,variables={}) {
  const span=doc.createElement('span');
  span.dataset.i18n=key;
  span.dataset.i18nVars=JSON.stringify(variables);
  span.textContent=t(key,variables);
  return span;
}
function localButton(doc,key,iconName) {
  const button=doc.createElement('button');button.type='button';button.className='ui-table-button';button.dataset.tableControl='true';
  if(iconName)button.innerHTML=uiIcon(iconName,{size:17});
  button.append(localLabel(doc,key));return button;
}
function readCell(cell) {
  const content=cell.querySelector('.ui-cell-content') || cell;
  // A raw sort attribute is optional and used only for ordering; never change
  // what the user sees or infer a unit from the displayed value.
  return cell.dataset.sortValue ?? content.textContent ?? '';
}
function defaultValueViewer(doc,value) {
  const dialog=doc.createElement('dialog');dialog.className='ui-value-dialog';
  const heading=doc.createElement('h2');heading.append(localLabel(doc,'UI v14.table.completeValue'));
  const body=doc.createElement('pre');body.className='ui-value-text';body.textContent=value;
  const close=localButton(doc,'UI v14.table.close','close');
  dialog.setAttribute('aria-label',t('UI v14.table.completeValue'));dialog.dataset.i18nAriaLabel='UI v14.table.completeValue';
  dialog.append(heading,body,close);doc.body.append(dialog);
  close.addEventListener('click',()=>dialog.close());dialog.addEventListener('close',()=>dialog.remove(),{once:true});
  dialog.showModal();close.focus();
}
export function enhanceTable(table,{pageSize=10,pageSizes=[10,25,50],minRows=6,fullTextThreshold=120,onViewValue}={}) {
  if(controllers.has(table))return controllers.get(table);
  if(!table?.ownerDocument||table.tBodies.length!==1||!table.tHead)return null;
  const tbody=table.tBodies[0],headers=Array.from(table.tHead.rows.at?.(-1)?.cells || table.tHead.rows[table.tHead.rows.length-1]?.cells || []);
  if(!headers.length || headers.some(cell=>cell.colSpan!==1))return null;
  const rows=Array.from(tbody.rows).filter(row=>!row.hidden);
  if(!rows.length || rows.some(row=>row.cells.length!==headers.length||Array.from(row.cells).some(cell=>cell.colSpan!==1)))return null;
  tableView([],{pageSize});
  const sizes=[...new Set([pageSize,...pageSizes])].filter(size=>Number.isInteger(size)&&size>=1&&size<=500).sort((a,b)=>a-b);
  const doc=table.ownerDocument,originalClass=table.className,originalEnhanced=table.getAttribute('data-ui-table-enhanced');
  table.classList.add('ui-data-table');table.dataset.uiTableEnhanced='true';
  const wrapper=table.parentElement,wrapperHadClass=wrapper?.classList.contains('ui-table-scroll');wrapper?.classList.add('ui-table-scroll');
  const state={filter:'',sortColumn:null,sortDirection:'none',page:1,pageSize};
  const columnTypes=headers.map(cell=>cell.dataset.sort || 'auto');
  const longCells=[],sortHeaders=[];
  const toolbar=doc.createElement('div');toolbar.className='ui-table-toolbar';toolbar.setAttribute('role','group');toolbar.dataset.i18nAriaLabel='UI v14.table.controls';
  const filterLabel=doc.createElement('label');filterLabel.className='ui-table-filter';filterLabel.append(localLabel(doc,'UI v14.table.filter'));
  const filter=doc.createElement('input');filter.type='search';filter.maxLength=1024;filter.dataset.tableControl='true';filter.dataset.i18nPlaceholder='UI v14.table.filterPlaceholder';filter.setAttribute('autocomplete','off');filterLabel.append(filter);
  const clear=localButton(doc,'UI v14.table.clearFilter','close');
  const sizeLabel=doc.createElement('label');sizeLabel.className='ui-table-page-size';sizeLabel.append(localLabel(doc,'UI v14.table.rowsPerPage'));
  const sizeSelect=doc.createElement('select');sizeSelect.dataset.tableControl='true';
  for(const size of sizes){const option=doc.createElement('option');option.value=String(size);option.textContent=String(size);option.selected=size===pageSize;sizeSelect.append(option);}sizeLabel.append(sizeSelect);
  toolbar.append(filterLabel,clear,sizeLabel);
  const footer=doc.createElement('div');footer.className='ui-table-footer';
  const summary=doc.createElement('span');summary.className='ui-table-summary';summary.setAttribute('role','status');summary.setAttribute('aria-live','polite');summary.setAttribute('aria-atomic','true');
  const pager=doc.createElement('div');pager.className='ui-table-pager';
  const previous=localButton(doc,'UI v14.table.previous','previous'),next=localButton(doc,'UI v14.table.next','next'),pageLabel=localLabel(doc,'UI v14.table.page',{page:1,pages:1});
  pager.append(previous,pageLabel,next);footer.append(summary,pager);
  const insertionTarget=wrapper?.tagName==='DIV'?wrapper:table;
  insertionTarget.before(toolbar);insertionTarget.after(footer);
  toolbar.hidden=rows.length<minRows&&rows.length<=pageSize;footer.hidden=toolbar.hidden;
  const empty=doc.createElement('tr');empty.dataset.tableControl='true';empty.className='ui-table-empty';
  const emptyCell=doc.createElement('td');emptyCell.colSpan=headers.length;emptyCell.append(localLabel(doc,'UI v14.table.noMatches'));empty.append(emptyCell);tbody.append(empty);
  const headerText=index=>sortHeaders.find(item=>item.index===index)?.label.textContent.trim()||headers[index].textContent.trim();
  headers.forEach((header,index)=>{
    if(columnTypes[index]==='none'||!header.textContent.trim())return;
    const originalNodes=Array.from(header.childNodes),originalSort=header.getAttribute('aria-sort');
    const button=doc.createElement('button');button.type='button';button.className='ui-table-sort';
    const label=doc.createElement('span');label.className='ui-table-column-label';label.append(...originalNodes);
    const indicator=doc.createElement('span');indicator.className='ui-sort-indicator';indicator.setAttribute('aria-hidden','true');button.append(label,indicator);header.append(button);
    button.addEventListener('click',()=>{const direction=state.sortColumn!==index?'ascending':state.sortDirection==='ascending'?'descending':state.sortDirection==='descending'?'none':'ascending';controller.setSort(index,direction);});
    sortHeaders.push({header,button,label,indicator,index,originalNodes,originalSort});
  });
  rows.forEach((row,rowIndex)=>Array.from(row.cells).forEach((cell,column)=>{
    const original=cell.textContent || '';
    if(original.length<=fullTextThreshold || cell.querySelector('button,a,input,select,textarea'))return;
    const nodes=Array.from(cell.childNodes),content=doc.createElement('div');content.className='ui-cell-content';content.append(...nodes);
    const button=localButton(doc,'UI v14.table.viewComplete','eye');button.classList.add('ui-cell-view');
    button.addEventListener('click',()=>{
      const value=content.textContent || '',context={column:headerText(column),rowIndex};
      if(onViewValue)onViewValue(value,context);else defaultValueViewer(doc,value);
    });cell.append(content,button);longCells.push({cell,nodes,content,button});
  }));
  let current;
  function draw(){
    const values=rows.map(row=>Array.from(row.cells,readCell));
    const searchRows=rows.map(row=>Array.from(row.cells,cell=>(cell.querySelector('.ui-cell-content') || cell).textContent || ''));
    current=tableView(values,{...state,columnTypes,searchRows,locale:getLanguage()});state.page=current.page;
    const visible=new Set(current.rowIndexes),matched=new Set(current.allIndexes);
    for(const index of [...current.allIndexes,...rows.map((_,index)=>index).filter(index=>!matched.has(index))]){const row=rows[index];row.hidden=!visible.has(index);tbody.append(row);}
    empty.hidden=current.filtered!==0;tbody.append(empty);
    const variables={start:current.start,end:current.end,filtered:current.filtered,total:current.total};
    summary.replaceChildren(localLabel(doc,'UI v14.table.summary',variables));
    pageLabel.dataset.i18nVars=JSON.stringify({page:current.page,pages:current.pages});pageLabel.textContent=t('UI v14.table.page',{page:current.page,pages:current.pages});
    previous.disabled=current.page===1;next.disabled=current.page===current.pages;clear.disabled=!state.filter;
    sortHeaders.forEach(item=>{const direction=state.sortColumn===item.index?state.sortDirection:'none';item.header.setAttribute('aria-sort',direction);item.button.setAttribute('aria-label',t('UI v14.table.sort',{column:headerText(item.index)}));item.indicator.innerHTML=uiIcon(direction==='ascending'?'chevronUp':direction==='descending'?'chevronDown':'sort',{size:16});});
    translateMarked(toolbar);translateMarked(footer);return {...current,rowIndexes:[...current.rowIndexes],allIndexes:[...current.allIndexes]};
  }
  const controller={
    setFilter(value){state.filter=String(value ?? '');filter.value=state.filter;state.page=1;return draw();},
    setSort(column,direction='ascending'){if(column!==null&&(!Number.isInteger(column)||column<0||column>=headers.length||!sortHeaders.some(item=>item.index===column)))throw new RangeError('Unsupported table sort column.');tableView([],{sortColumn:column,sortDirection:direction,pageSize:state.pageSize});state.sortColumn=column;state.sortDirection=direction;state.page=1;return draw();},
    setPage(page){tableView([],{page,pageSize:state.pageSize});state.page=page;return draw();},
    setPageSize(size){tableView([],{pageSize:size});state.pageSize=size;sizeSelect.value=String(size);state.page=1;return draw();},
    refresh(){return draw();},
    captureState(){return {...state};},
    restoreState(snapshot){
      const restored=validatedTableState(snapshot,{columnCount:headers.length,sortableColumns:sortHeaders.map(item=>item.index)});
      // Validate the complete snapshot before changing any control or state.
      Object.assign(state,restored);filter.value=state.filter;
      if(!Array.from(sizeSelect.options).some(option=>Number(option.value)===state.pageSize)){
        const option=doc.createElement('option');option.value=String(state.pageSize);option.textContent=String(state.pageSize);sizeSelect.append(option);
      }
      sizeSelect.value=String(state.pageSize);return draw();
    },
    getState(){return {...state,...current,rowIndexes:[...current.rowIndexes],allIndexes:[...current.allIndexes]};},
    destroy(){
      rows.forEach(row=>{row.hidden=false;tbody.append(row);});empty.remove();toolbar.remove();footer.remove();
      sortHeaders.forEach(item=>{item.header.replaceChildren(...item.originalNodes);if(item.originalSort===null)item.header.removeAttribute('aria-sort');else item.header.setAttribute('aria-sort',item.originalSort);});
      longCells.forEach(item=>item.cell.replaceChildren(...item.nodes));
      table.className=originalClass;if(!wrapperHadClass)wrapper?.classList.remove('ui-table-scroll');if(originalEnhanced===null)table.removeAttribute('data-ui-table-enhanced');else table.setAttribute('data-ui-table-enhanced',originalEnhanced);controllers.delete(table);
    },
  };
  filter.addEventListener('input',()=>controller.setFilter(filter.value));clear.addEventListener('click',()=>{controller.setFilter('');filter.focus();});
  sizeSelect.addEventListener('change',()=>controller.setPageSize(Number(sizeSelect.value)));previous.addEventListener('click',()=>controller.setPage(Math.max(1,state.page-1)));next.addEventListener('click',()=>controller.setPage(Math.min(current.pages,state.page+1)));
  controllers.set(table,controller);draw();return controller;
}
function actualTables(root){
  if(!root?.querySelectorAll)return [];
  return [...(root.matches?.('table')?[root]:[]),...root.querySelectorAll('table')].filter(table=>!table.hasAttribute('data-no-enhance'));
}
export function enhanceTables(root=globalThis.document,options={}) {return actualTables(root).map(table=>enhanceTable(table,options)).filter(Boolean);}
export function refreshEnhancedTables(root=globalThis.document){return actualTables(root).map(table=>controllers.get(table)?.refresh()).filter(Boolean);}
