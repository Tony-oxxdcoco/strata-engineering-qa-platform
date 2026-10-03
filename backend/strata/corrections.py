"""Explicit scalar corrections; never overwrite a stored source or snapshot."""
import json
import re

from .storage import canonical, digest


def apply_corrections(original, corrections):
    if not isinstance(corrections, list) or not 1 <= len(corrections) <= 50:
        raise ValueError("Provide 1–50 explicit field corrections")
    result = json.loads(canonical(original))
    seen = set()
    for change in corrections:
        if not isinstance(change, dict) or set(change) != {"path", "original", "value", "source_locator", "reason"}:
            raise ValueError("Each correction needs path, original, value, source_locator and reason")
        path = change["path"]
        if not isinstance(path, str) or not path.startswith("/") or len(path) > 500 or re.search(r"~(?![01])", path):
            raise ValueError("Use a valid JSON Pointer for the corrected scalar")
        if path in seen or path in {"/synthetic", "/schema", "/schemaVersion"}:
            raise ValueError("Duplicate path or protected provenance field")
        seen.add(path)
        for key in ["source_locator", "reason"]:
            if not isinstance(change[key], str) or not 1 <= len(change[key].strip()) <= 1000:
                raise ValueError("Every correction needs an inspectable source location and reason")
        for key in ["original", "value"]:
            value = change[key]
            if isinstance(value, (dict, list)):
                raise ValueError("Correct scalar fields individually; use an explicit mapping for structural changes")
            canonical(value)
        parts = [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]
        node = result
        try:
            for part in parts[:-1]:
                if isinstance(node, list):
                    if not re.fullmatch(r"0|[1-9][0-9]*", part):
                        raise ValueError("Invalid array index")
                    node = node[int(part)]
                else:
                    node = node[part]
            key = parts[-1]
            if isinstance(node, list):
                if not re.fullmatch(r"0|[1-9][0-9]*", key):
                    raise ValueError("Invalid array index")
                key = int(key)
            if digest(node[key]) != digest(change["original"]):
                raise ValueError("Original field value no longer matches the selected snapshot")
            node[key] = change["value"]
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError("Correction path does not address an existing scalar") from error
    return result
