import test from 'node:test';
import assert from 'node:assert/strict';
import {withinTolerance,runChecks} from '../dist/engine.js';
import {getSample} from '../dist/samples.js';
import {runCombinationChecks,getCombinationSample} from '../dist/combinations.js';
test('closed gravity tolerance does not widen by an arbitrary epsilon',()=>{
 assert.equal(withinTolerance(101,100),true);
 assert.equal(withinTolerance(101+1e-10,100),false);
 assert.equal(withinTolerance(99-1e-10,100),false);
});
test('nonzero engineering multiplication cannot underflow to zero',()=>{
 const d=getSample('clean');d.floors[0].area=1e-200;d.requirements[0].q=1e-200;
 assert.throws(()=>runChecks(d),/underflow/);
});
test('renaming identical source content does not establish an independent combination baseline',()=>{
 const d=getCombinationSample('clean');
 const combo=d.combinations[0],base=d.baseCases.find(b=>b.caseId===combo.terms[0].caseId||b.id===combo.terms[0].caseId);
 const reported=d.evidence.find(e=>e.id===combo.evidenceRef),original=d.evidence.find(e=>e.id===base.evidenceRef);
 original.content=reported.content;original.locator=reported.locator;
 assert.equal(runCombinationChecks(d).results[0].status,'NOT VERIFIED');
});
