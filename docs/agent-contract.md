# Controlled local QA workflow contract

This module is an implemented **controlled local workflow**, not a live LLM agent or production RAG service. It orchestrates the existing deterministic gravity/combination engines and curated synthetic rule retrieval. It does not call ETABS, SAFE, a model API or any network endpoint. The working engineering-data provider is `controlled-file`; every other provider is blocked explicitly.

## Public interface

```js
import {
  AGENT_VERSION, AGENT_TASKS, AGENT_TOOLS, AGENT_CALL_BUDGET,
  executeAgent, validateModelTaskProposal, agentReport, runAgentValidation,
} from './agent.js';

const run = await executeAgent({
  taskId: 'gravity-full',
  input,                       // existing gravity schema or combination-1.0
  corpus,                      // getDemoKnowledge() when omitted
  dataMode: 'controlled-file',
});
const markdown = await agentReport(run);
```

`AGENT_TASKS` contains `{id,title,description,ruleIds}`:

| Task ID | Required rule IDs | Returned findings |
| --- | --- | --- |
| gravity-full | QA-001 through QA-006 | Six existing gravity checks |
| gravity-distribution | QA-003 | Floor distribution only |
| gravity-balance | QA-005 | Independent vertical reaction balance only |
| load-combination | COMB-001 | One finding per supplied linear combination |

For individual gravity tasks the registered existing engine computes its dependencies and the workflow selects the requested finding. COMB-001 is a method definition, so valid custom combination IDs use the same bounded calculation; the shipped C1/C2 IDs do not limit the method or imply approved design factors.

The immutable returned run contains `version`, `versions`, `id`, `createdAt`, `taskId`, `task:{id,title}`, `dataMode`, input/corpus snapshots, `inputHash`, `corpusHash`, `runHash`, `status`, `summary:{PASS,FAIL,'NOT VERIFIED'}`, `results`, `citations`, `explanation`, `toolTrace`, `callsUsed`, `callBudget`, rejected `requestFields`, and the explicit `scope` statement. All nested values are frozen. Editing the original request after invocation cannot alter the saved run. Findings use the engines' result/detail fields; the evidence stage also records their rule IDs.

The input and corpus hashes are SHA-256 of their saved JSON serialisations; property order is significant and JSON normalises negative zero to zero. `runHash` covers the entire saved run except itself. These hashes detect inconsistent snapshots; they are not signatures, authenticated source provenance or protection against an attacker who can replace the application.

## Fixed orchestration and trace

The tool allowlist and maximum executed call count are both fixed in code. Callers cannot override them or supply tool implementations or arguments. Every run shows the following five positions in order:

1. `retrieve_engineering_rules`: retrieves the complete required rule set for the registered task. The knowledge module checks each source, scope, version, approval label and task binding against shipped synthetic definitions. Missing, retired, modified, conflicting or unsupported rules block the run.
2. `request_engineering_data`: validates an explicitly synthetic input snapshot using its engine schema. Only the controlled-file adapter is available. Selecting ETABS/SAFE or an arbitrary provider produces NOT VERIFIED, with no silent fallback.
3. `run_deterministic_check`: calls exactly one registered checking engine. This position is **skipped, not called**, if rule retrieval or the input/provider gate failed.
4. `verify_evidence`: retains engine findings and their rule binding. Missing cited source records can downgrade PASS to NOT VERIFIED; they cannot upgrade a result. If no calculation ran, it emits an explicit AGENT-GATE NOT VERIFIED finding.
5. `compose_response`: constructs a fixed explanation template using the checked status, counts, findings, numbers and exact retrieved rule citations. There is no free-form generative interpretation.

Each trace step is `{index,tool,status,called,inputs,outputs,sources,errors,durationMs}`. Status is `ok`, `blocked`, `skipped` or `error`; `called:false` means no tool ran and duration is zero. Successful checked mismatches are ordinary completed tool calls, not software errors. Elapsed durations are local measurements for that execution, not performance benchmarks. The call budget is five. No retry, recursion or model-chosen chain occurs. Blocked runs still verify the gate and compose a clear NOT VERIFIED response; fewer than five calls are then executed.

Malformed non-JSON request data (for example NaN, cycles or sparse arrays) throws before execution to prevent lossy serialisation. Ordinary JSON input-schema errors are recorded as data-tool errors and produce NOT VERIFIED without a calculation call. Empty/missing/invalid rule content and unknown tasks also fail closed. Unsupported numeric-engine scope remains subject to that engine's NOT VERIFIED gates.

## Model-output boundary

`validateModelTaskProposal(proposal)` only accepts `{taskId}` for one of the four registered IDs. It returns `{accepted,taskId,reason}`. Unknown tasks or additional keys such as `status`, `findings`, `explanation`, `tool`, `args` or numerical overrides are rejected. `executeAgent` separately rejects request keys outside `taskId,input,corpus,dataMode`; therefore a caller cannot bypass the selection validator by adding claimed findings to the workflow request.

Any future model router must use the selection validator and pass only an accepted task ID. The saved engineering input, curated corpus, tool arguments and outcomes remain controlled locally. Imported evidence text is data, not instructions. The shipped knowledge rules are explicitly synthetic and demo-approved, not client-approved standards. This implementation does not claim that an LLM has been tested, that retrieval eliminates hallucination, or that any factors establish code compliance.

## Verified report and validation

`agentReport(run)` snapshots once, checks the run/input/corpus hashes, re-executes the same request and compares all technical fields, citations, explanation, versions, call counts and trace semantics. It validates historical timing values but does not compare new execution times with old ones. Changed results, changed source text, stale versions, altered inputs and inconsistent traces are rejected. The Markdown contains all engineering source records, exact retrieved rule text, calculation details, the complete tool trace and both input/corpus snapshots. It is labelled DRAFT — NOT ENGINEERING APPROVAL. There is no fabricated engineer review or signature.

`runAgentValidation()` executes a fixed local suite and returns:

```text
{generatedAt, summary:{total,matched,mismatched},
 cases:[{id,title,expected,actual,matched,reason}]}
```

Its ten handwritten expectations cover clean/failed/missing-evidence gravity cases, clean/failed/missing-reference combinations, empty knowledge, unavailable ETABS, an unknown task, and rejection of a model claim while the actual combination mismatch remains FAIL. Missing-rule/provider/task fixtures also assert that no deterministic check was called. This is an observable software validation suite using synthetic fixtures, not measured engineering accuracy on client data.

Run `node --test tests/agent.test.mjs` for the workflow, gating, provenance and replay tests. Existing gravity and combination suites validate their numerical methods separately.
