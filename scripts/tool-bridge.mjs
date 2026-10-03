// JSON-in/JSON-out boundary, called with a timeout by the application server.
import {runChecks} from '../dist/engine.js';
import {runCombinationChecks, getCombinationSample} from '../dist/combinations.js';
import {getSample} from '../dist/samples.js';
import {getDemoKnowledge} from '../dist/knowledge.js';
import {parseControlledCsv} from '../dist/csv.js';
import {runValidation} from '../dist/validation.js';
import {runAgentValidation} from '../dist/agent.js';
let text = '';
process.stdin.setEncoding('utf8');
for await (const chunk of process.stdin) { text += chunk; if (text.length > 2_000_000) throw Error('Input limit'); }
try {
  const req = JSON.parse(text);
  let result;
  if (req.tool === 'seed') result = {gravity:getSample(req.profile === 'combination' ? 'clean' : req.scenario || 'clean'), combination:getCombinationSample(req.profile === 'gravity' ? 'clean' : req.scenario || 'clean'), knowledge:getDemoKnowledge()};
  else if (req.tool === 'csv') result = parseControlledCsv(req.text, {filename:req.filename});
  else if (req.tool === 'gravity') result = runChecks(req.input);
  else if (req.tool === 'combination') result = runCombinationChecks(req.input);
  else if (req.tool === 'validation') result = {engineering:runValidation(),agent:await runAgentValidation()};
  else throw Error('Unregistered tool');
  process.stdout.write(JSON.stringify({ok:true,result}));
} catch (error) {process.stdout.write(JSON.stringify({ok:false,error:error.message})); process.exitCode = 1;}
