# Structured synthetic rule retrieval

This module provides exact task/rule filtering and small lexical full-text ranking over seven curated synthetic rule records. It is retrieval groundwork for a later RAG workflow. It does **not** run an LLM, use embeddings or a vector index, interpret a free-text task, access ETABS, approve engineering rules or claim structural compliance.

## Interfaces

```js
import {
  getDemoKnowledge, validateKnowledgeCorpus, retrieveRules, searchRules,
  KNOWLEDGE_VERSION, KNOWLEDGE_TASKS
} from './knowledge.js';

const corpus = getDemoKnowledge(); // fresh JSON-compatible copy
const checkedCorpus = validateKnowledgeCorpus(corpus); // fresh validated copy, or Error
const context = retrieveRules({ taskId: 'gravity-distribution', corpus });
const matches = searchRules({ query: 'reaction balance', corpus, limit: 5 });
```

Both retrieval functions return `{ status, reason, rules, citations }`. `status` is `FOUND` or `NOT VERIFIED`. A blocked result always has empty `rules` and `citations`; it cannot silently expose partial context for a complete task. `FOUND` means source retrieval succeeded, **not** that any engineering check passed.

`retrieveRules({ taskId, corpus, ruleIds?, version?, scope?, query? })` requires a registered exact task ID. Optional rule IDs, version and scope are exact filters. Every required task rule must remain active and available after filtering. Optional query text changes display ranking only; it cannot remove required rules or supply missing ones.

`searchRules({ query, corpus, taskId?, ruleIds?, version?, scope?, limit? })` is for browsing. It returns only lexical matches, so its result does not authorize task execution. `limit` defaults to 10 and must be 1–100; query text is limited to 500 characters. Ranking sums literal query-token matches in rule/check IDs (weight 8), source title (4), locator (2) and source text (1), then breaks ties by rule ID. No search relevance or engineering-accuracy performance claim is made.

If `corpus` is omitted, the shipped corpus is used. Pass an explicit empty corpus or `null` to represent unavailable imported knowledge; do not replace an invalid import with the default corpus. All invalid retrieval inputs fail closed. `validateKnowledgeCorpus` throws a descriptive Error; callers may retain the rejected raw import for displaying its error, but must pass it through retrieval before running a tool. A UI file loader should reject JSON files above 1 MiB before parsing.

## Corpus contract and trust boundary

```js
{
  schemaVersion: 'knowledge-1.0',
  synthetic: true,
  authority: 'SYNTHETIC',
  purpose: 'controlled-demo',
  version: 'knowledge-demo-1.0.0',
  rules: [{
    id: 'QA-003',
    version: 'DEMO-2026.09',
    authority: 'SYNTHETIC',
    approval: 'demo-approved',
    status: 'active', // or retired
    scope: 'gravity-unfactored-static-excluding-self-weight',
    source: { title: '...', locator: '...', text: '...' },
    checkIds: ['QA-003'],
    taskIds: ['gravity-full', 'gravity-distribution']
  }]
}
```

The example above illustrates the shape; use `getDemoKnowledge()` or `examples/demo-knowledge.json` for the full exact records. At most 100 records are accepted. Unknown fields, new rule IDs, unsupported versions, changed scopes, altered applicability, missing/changed source text and customer-approval claims are rejected. Record identity and source content must match the curated definitions shipped with this module. The label `demo-approved` means only that this demonstration ships that definition; a caller cannot approve a new or edited rule by writing that label.

An input may remove a rule or mark it `retired`, which can make a task unavailable. Duplicate rule definitions are ambiguous and reject the corpus, including identical duplicates; the module never silently picks the first, latest or most relevant competing record. Required missing or retired rules produce `NOT VERIFIED`. An empty rule list is valid as an empty corpus but supplies no task context.

Source text is data, not instructions. This module does not execute it or allow it to change tool names, arguments, factors, tolerances or verification outcomes. Imported text that asks for such changes will fail the exact curated-content check. This local check is not a digital signature or a general solution to prompt injection: future client knowledge ingestion needs an independently controlled review/version workflow.

## Registered task coverage

| Task | Required rule IDs | Demonstration check IDs |
| --- | --- | --- |
| `gravity-full` | `QA-001` through `QA-006` | same six IDs |
| `gravity-distribution` | `QA-003` | `QA-003` |
| `gravity-balance` | `QA-005` | `QA-005` |
| `load-combination` | `COMB-001` | `C1`, `C2` |

Gravity rules use the current engine `RULE_VERSION` and the scope `gravity-unfactored-static-excluding-self-weight`. The combination rule uses `COMBINATION_VERSION` and `linear-static-combination-response`. `C1` and `C2` identify the shipped combination examples. The same deterministic sum method can apply to other explicitly supplied IDs allowed by the combination tool contract; retrieval does not approve the supplied factors or expand supported analysis types.

## Citations and workflow integration

Each returned rule retains `source: {title, locator, text}`. Each corresponding citation is:

```js
{
  ruleId: 'QA-003', version: 'DEMO-2026.09',
  authority: 'SYNTHETIC', approval: 'demo-approved',
  scope: 'gravity-unfactored-static-excluding-self-weight',
  title: '...', locator: '...', quote: '...'
}
```

`quote` is the exact complete curated `source.text`. It is not generated or paraphrased. UI code should render these strings as text. The execution workflow must gate on complete `retrieveRules` context, validate tool requests separately, and retain the corpus/version and returned citations with the run. Engineering input evidence remains a separate requirement: finding a rule does not make missing model data or reaction evidence valid.
