"""Project-scoped, approval-gated lexical retrieval; Python standard library only.

validate_rule returns a fresh JSON record or raises ValueError. Unknown JSON fields
are preserved. Approval records a software review action, not engineering truth.
source_sha256 identifies the original file, not necessarily the text excerpt; the
storage layer must verify that file exists and matches its hash. Citations also
include a computed text_sha256, binding the exact quoted text.

retrieve uses English words/phrases and Chinese character n-grams with BM25. It
has no LLM, embeddings, network, code execution or automatic translation. FOUND
means relevant approved records were found, not that every mandatory check was
covered. Call check_coverage with the task's independently registered check IDs
before execution. Source text and optional parameters are inert data throughout.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import math
import re
import unicodedata


RETRIEVAL_VERSION = "lexical-bm25-1.0.0"
MAX_RULES = 5000
MAX_TEXT = 200_000
MAX_QUERY = 4096
MAX_LIMIT = 50
_STATUSES = {"draft", "approved", "retired"}
_AUTHORITIES = {"synthetic", "client"}
_HEX256 = re.compile(r"[0-9a-fA-F]{64}\Z")
_WORDS = re.compile(r"[a-z][a-z0-9]*|[0-9]+(?:\.[0-9]+)?")
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_EN_STOP = frozenset("""
a an and are as at be been by can could do does for from had has have how i if in
into is it its me my of on or our please rule rules check checks checking query
show should that the their them there these they this those to us was we were
what when where which who why will with would you your find tell explain about
""".split())
_ZH_STOP = re.compile("|".join((
    "请问", "帮我", "查找", "查询", "检查", "规则", "说明", "什么", "如何",
    "是否", "这个", "那个", "一个", "需要", "可以", "有关", "对于", "关于",
    "时候", "我们", "你们", "你的", "您好", "请", "的", "了", "吗", "呢",
)))


def _copy_json(value, depth=0):
    """Reject non-JSON values rather than silently coercing metadata."""
    if depth > 32:
        raise ValueError("Rule data exceeds the maximum JSON nesting depth")
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is list:
        return [_copy_json(item, depth + 1) for item in value]
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: _copy_json(item, depth + 1) for key, item in value.items()}
    raise ValueError("Rule data must contain only finite JSON values")


def _string(value, field, maximum=256, identifier=False):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field} must be a non-empty string of at most {maximum} characters")
    if identifier and (value != value.strip() or any(char.isspace() for char in value)):
        raise ValueError(f"{field} must not contain whitespace")
    if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
        raise ValueError(f"{field} must not contain control characters")
    # A lone surrogate cannot be encoded into a portable UTF-8 evidence hash.
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{field} must contain valid Unicode") from exc
    return value


def _identifiers(value, field):
    if type(value) is not list or not value or len(value) > 256:
        raise ValueError(f"{field} must be a non-empty list of at most 256 identifiers")
    for item in value:
        _string(item, field, 128, identifier=True)
    if len(set(value)) != len(value):
        raise ValueError(f"{field} must not contain duplicates")
    return value


def _timestamp(value):
    _string(value, "approved_at", 64)
    if "T" not in value:
        raise ValueError("approved_at must be an ISO date-time with timezone")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("approved_at must be an ISO date-time with timezone") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("approved_at must include a timezone")


def validate_rule(rule):
    """Validate and copy a rule, including required project and source metadata.

    Required keys: id, project_id, version, title, text, locator, task_ids,
    check_ids, status, authority, source_sha256, approved_by and approved_at.
    Draft/retired approval fields may be None. Approved rules require both.
    parameters, when present, must be a JSON object. No parameters are executed.
    """
    if type(rule) is not dict:
        raise ValueError("rule must be a JSON object")
    required = ("id", "project_id", "version", "title", "text", "locator",
                "task_ids", "check_ids", "status", "authority", "source_sha256",
                "approved_by", "approved_at")
    missing = [key for key in required if key not in rule]
    if missing:
        raise ValueError("Missing rule fields: " + ", ".join(missing))
    result = _copy_json(rule)
    for field in ("id", "project_id", "version"):
        _string(result[field], field, 128, identifier=True)
    _string(result["title"], "title", 512)
    _string(result["text"], "text", MAX_TEXT)
    _string(result["locator"], "locator", 2048)
    _identifiers(result["task_ids"], "task_ids")
    _identifiers(result["check_ids"], "check_ids")
    if type(result["status"]) is not str or result["status"] not in _STATUSES:
        raise ValueError("status must be draft, approved or retired")
    if type(result["authority"]) is not str or result["authority"] not in _AUTHORITIES:
        raise ValueError("authority must be synthetic or client")
    if type(result["source_sha256"]) is not str or not _HEX256.fullmatch(result["source_sha256"]):
        raise ValueError("source_sha256 must be a 64-character hexadecimal file hash")
    result["source_sha256"] = result["source_sha256"].lower()
    if result["approved_by"] is not None:
        _string(result["approved_by"], "approved_by", 256)
    if result["approved_at"] is not None:
        _timestamp(result["approved_at"])
    if result["status"] == "approved" and (
            result["approved_by"] is None or result["approved_at"] is None):
        raise ValueError("An approved rule requires approved_by and approved_at")
    if "parameters" in result and type(result["parameters"]) is not dict:
        raise ValueError("parameters must be a JSON object")
    return result


def _normal(text):
    return unicodedata.normalize("NFKC", text).lower()


def _tokens(text):
    normal = _normal(text)
    result = Counter()
    words = []
    for word in _WORDS.findall(normal):
        if word in _EN_STOP:
            continue
        # A small deterministic plural normalization, not a semantic model.
        if len(word) > 4 and word.endswith("s") and not word.endswith(("ss", "is", "us")):
            word = word[:-1]
        words.append(word)
        result["en:" + word] += 1
    for left, right in zip(words, words[1:]):
        result["phrase:" + left + " " + right] += 1
    for run in _CJK.findall(normal):
        for fragment in _ZH_STOP.split(run):
            for width in (1, 2, 3):
                for start in range(len(fragment) - width + 1):
                    result[f"zh{width}:" + fragment[start:start + width]] += 1
    return result


def _weight(token):
    if token.startswith("zh1:"):
        return 0.15
    if token.startswith("zh3:"):
        return 1.2
    if token.startswith("phrase:"):
        return 0.75
    return 1.0


def _exact_id(query, rule_id):
    # ASCII identifier boundaries allow IDs immediately after Chinese text.
    expression = r"(?<![a-z0-9_.-])" + re.escape(_normal(rule_id)) + r"(?![a-z0-9_.-])"
    return re.search(expression, _normal(query)) is not None


def _not_verified(reason):
    return {"status": "NOT VERIFIED", "rules": [], "citations": [],
            "reason": reason, "scores": []}


def _citation(rule):
    return {
        "rule_id": rule["id"], "project_id": rule["project_id"],
        "version": rule["version"], "title": rule["title"],
        "quote": rule["text"], "locator": rule["locator"],
        "source_sha256": rule["source_sha256"],
        "text_sha256": hashlib.sha256(rule["text"].encode("utf-8")).hexdigest(),
        "authority": rule["authority"], "status": rule["status"],
        "approved_by": rule["approved_by"], "approved_at": rule["approved_at"],
        "check_ids": list(rule["check_ids"]), "task_ids": list(rule["task_ids"]),
    }


def retrieve(query, task_id, rules, project_id, limit=5):
    """Return relevant approved rules in one caller-authorized project and task.

    The caller must authenticate project access before calling this pure function.
    'approved' is the active state; draft/retired are never candidates. Multiple
    approved versions, or conflicting contents for one id/version, fail closed
    within the requested project/task. An old version must be retired explicitly:
    version strings are opaque, and no version is silently selected as 'latest'.
    Invalid approved in-scope records also block retrieval. Other projects/tasks
    do not contribute tokens, scores, conflicts or citations. Scores are lexical
    ranking signals, not confidence or engineering truth probabilities.
    """
    try:
        _string(query, "query", MAX_QUERY)
        _string(task_id, "task_id", 128, identifier=True)
        _string(project_id, "project_id", 128, identifier=True)
        if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
            raise ValueError(f"limit must be an integer between 1 and {MAX_LIMIT}")
        if type(rules) is not list or len(rules) > MAX_RULES:
            raise ValueError(f"rules must be a list of at most {MAX_RULES} records")
    except ValueError as exc:
        return _not_verified(str(exc))

    eligible = {}
    for raw in rules:
        if type(raw) is not dict or raw.get("project_id") != project_id:
            continue
        if raw.get("status") != "approved":
            continue
        try:
            tasks = _identifiers(raw.get("task_ids"), "task_ids")
        except ValueError:
            return _not_verified("An approved project rule has invalid task scope")
        if task_id not in tasks:
            continue
        try:
            rule = validate_rule(raw)
        except ValueError as exc:
            return _not_verified("Invalid approved rule in requested scope: " + str(exc))
        previous = eligible.get(rule["id"])
        if previous is not None:
            if previous["version"] != rule["version"]:
                return _not_verified("Conflicting approved versions for rule " + rule["id"])
            if previous != rule:
                return _not_verified("Conflicting approved contents for rule " + rule["id"])
        else:
            eligible[rule["id"]] = rule
    if not eligible:
        return _not_verified("No valid approved sources for the requested project and task")

    ordered = sorted(eligible.values(), key=lambda rule: (rule["id"], rule["version"]))
    query_tokens = _tokens(query)
    documents = [_tokens(rule["title"] + "\n" + rule["text"]) for rule in ordered]
    # Check identifiers are indivisible tokens: QA-003 must not match QA-004
    # through a shared "QA" fragment. This supports custom client rule IDs.
    for rule, document in zip(ordered, documents):
        for check_id in rule["check_ids"]:
            token = "check:" + _normal(check_id)
            document[token] += 1
            if _exact_id(query, check_id):
                query_tokens[token] = 1
    lengths = [sum(document.values()) for document in documents]
    average_length = sum(lengths) / len(lengths) or 1.0
    frequencies = Counter(token for document in documents for token in document)
    # Single-character Chinese queries are supported; a long unrelated Chinese
    # query cannot match solely because one common character appears in a rule.
    single_character_query = len(_normal(query).strip()) == 1
    ranked = []
    for rule, document, length in zip(ordered, documents, lengths):
        matches = sorted(set(query_tokens) & set(document))
        exact = _exact_id(query, rule["id"])
        exact_checks = sorted(check_id for check_id in rule["check_ids"] if _exact_id(query, check_id))
        meaningful = any(not token.startswith("zh1:") for token in matches)
        if not exact and not meaningful and not (single_character_query and matches):
            continue
        contributions = {}
        for token in matches:
            frequency = document[token]
            idf = math.log1p((len(documents) - frequencies[token] + 0.5) /
                             (frequencies[token] + 0.5))
            denominator = frequency + 1.2 * (1 - 0.75 + 0.75 * length / average_length)
            contributions[token] = round(_weight(token) * idf * frequency * 2.2 / denominator, 12)
        bm25 = round(sum(contributions.values()), 12)
        score = round(bm25 + (1000.0 if exact else 0.0) + 100.0 * len(exact_checks), 12)
        ranked.append((rule, {
            "rule_id": rule["id"], "version": rule["version"], "score": score,
            "bm25": bm25, "exact_id": exact, "matched_tokens": matches,
            "token_scores": contributions, "matched_check_ids": exact_checks,
        }))
    if not ranked:
        return _not_verified("No lexical evidence matches the query in the approved scope")
    ranked.sort(key=lambda item: (-item[1]["score"], item[0]["id"], item[0]["version"]))
    selected = ranked[:limit]
    return {
        "status": "FOUND", "rules": [_copy_json(rule) for rule, _ in selected],
        "citations": [_citation(rule) for rule, _ in selected],
        "reason": "Relevant approved sources retrieved; verify source files and mandatory check coverage before execution",
        "scores": [_copy_json(score) for _, score in selected],
    }


def check_coverage(retrieval_result, required_check_ids):
    """Check ALL required IDs against approved retrieved rules, without execution.

    Required IDs come from a trusted task registry, never from model/source text.
    This checks declared coverage only, not file existence, caller permissions,
    engineering applicability, or whether an implementation exists for a rule.
    """
    covered, missing, rule_ids = [], [], []
    try:
        required = _identifiers(required_check_ids, "required_check_ids")
        missing = list(required)
        if type(retrieval_result) is not dict or retrieval_result.get("status") != "FOUND":
            raise ValueError("Retrieval did not find approved sources")
        raw_rules = retrieval_result.get("rules")
        if type(raw_rules) is not list or not raw_rules:
            raise ValueError("Retrieval contains no rules")
        found = [validate_rule(rule) for rule in raw_rules]
        if any(rule["status"] != "approved" for rule in found):
            raise ValueError("Coverage requires approved rules")
        if len({rule["project_id"] for rule in found}) != 1:
            raise ValueError("Coverage must not combine different projects")
        seen = {}
        for rule in found:
            if rule["id"] in seen and seen[rule["id"]] != rule:
                raise ValueError("Coverage contains conflicting approved rules")
            seen[rule["id"]] = rule
        available = {check for rule in found for check in rule["check_ids"]}
        covered = [check for check in required if check in available]
        missing = [check for check in required if check not in available]
        rule_ids = sorted({rule["id"] for rule in found if set(rule["check_ids"]) & set(required)})
        if missing:
            raise ValueError("Missing approved evidence for required checks: " + ", ".join(missing))
        return {"status": "FOUND", "covered_check_ids": covered,
                "missing_check_ids": [], "rule_ids": rule_ids,
                "reason": "All required checks have declared approved rule coverage; source and execution gates still apply"}
    except ValueError as exc:
        return {"status": "NOT VERIFIED", "covered_check_ids": covered,
                "missing_check_ids": missing, "rule_ids": rule_ids, "reason": str(exc)}
