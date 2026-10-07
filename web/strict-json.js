// Untrusted configuration JSON must be checked BEFORE JSON.stringify/API use.
// Native JSON.parse silently keeps the last duplicate field and converts a
// nonzero 1e-999 to zero. Only string-token decoding uses native JSON.parse.
export const MAX_JSON_BYTES = 10 * 1024 * 1024;
export const MAX_JSON_DEPTH = 32;

export class StrictJSONError extends SyntaxError {
  constructor(code, reason, text, offset, path) {
    const prefix = typeof text === 'string' ? text.slice(0, offset) : '';
    const lines = prefix.split(/\r\n|\r|\n/);
    const line = lines.length, column = lines.at(-1).length + 1;
    super(`Strict JSON error: ${reason} at line ${line}, column ${column}, path ${path || '/'}.`);
    this.name = 'StrictJSONError';
    Object.assign(this, {code, reason, offset, path: path || '/', line, column});
  }
}

const tokenFor = key => String(key).replace(/~/g, '~0').replace(/\//g, '~1');

export function parseStrictJSON(text, {maxBytes = MAX_JSON_BYTES, maxDepth = MAX_JSON_DEPTH} = {}) {
  let position = 0;
  const fail = (code, reason, path = '', offset = position) => {
    throw new StrictJSONError(code, reason, text, offset, path);
  };
  if (typeof text !== 'string') fail('INPUT_TYPE', 'JSON input must be text.');
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1 || maxBytes > MAX_JSON_BYTES ||
      !Number.isSafeInteger(maxDepth) || maxDepth < 0 || maxDepth > MAX_JSON_DEPTH) {
    throw new TypeError('Strict JSON limits must be bounded positive bytes and a depth of 0–32.');
  }
  // Reject obviously oversized input before allocating its UTF-8 copy.
  if (text.length > maxBytes || new TextEncoder().encode(text).length > maxBytes) {
    fail('SIZE_LIMIT', 'JSON exceeds the configured size limit.');
  }
  const whitespace = () => { while (position < text.length && /[ \t\n\r]/.test(text[position])) position++; };

  function string(path) {
    const start = position++;
    while (position < text.length) {
      const code = text.charCodeAt(position);
      if (text[position] === '"') {
        position++;
        let decoded;
        try { decoded = JSON.parse(text.slice(start, position)); }
        catch { fail('SYNTAX', 'Invalid JSON syntax.', path, start); }
        // The backend hashes UTF-8 source evidence. Unpaired surrogates cannot
        // be preserved portably and must not become replacement characters.
        for (let i = 0; i < decoded.length; i++) {
          const value = decoded.charCodeAt(i);
          if (value >= 0xD800 && value <= 0xDBFF) {
            const next = decoded.charCodeAt(++i);
            if (!(next >= 0xDC00 && next <= 0xDFFF)) fail('UNICODE', 'JSON strings must contain valid Unicode.', path, start);
          } else if (value >= 0xDC00 && value <= 0xDFFF) fail('UNICODE', 'JSON strings must contain valid Unicode.', path, start);
        }
        return decoded;
      }
      if (code < 0x20) fail('SYNTAX', 'Invalid JSON syntax.', path);
      if (text[position] === '\\') {
        const escaped = text[position + 1];
        if (escaped === 'u') {
          if (!/^[0-9a-fA-F]{4}$/.test(text.slice(position + 2, position + 6))) {
            fail('STRING_ESCAPE', 'Invalid JSON string escape.', path);
          }
          position += 6;
        } else {
          if (!escaped || !'"\\/bfnrt'.includes(escaped)) fail('STRING_ESCAPE', 'Invalid JSON string escape.', path);
          position += 2;
        }
      } else position++;
    }
    fail('UNTERMINATED_STRING', 'Unterminated JSON string.', path, start);
  }

  function value(path, depth) {
    whitespace();
    if (depth > maxDepth) fail('DEPTH_LIMIT', `JSON nesting exceeds ${maxDepth} levels.`, path);
    const character = text[position];
    if (character === '"') return string(path);
    if (character === '{') {
      position++; whitespace();
      const object = {}, seen = new Set();
      if (text[position] === '}') { position++; return object; }
      while (true) {
        if (text[position] !== '"') fail('OBJECT_KEY', 'Expected a JSON object field name.', path);
        const keyOffset = position, key = string(path), childPath = path + '/' + tokenFor(key);
        if (seen.has(key)) fail('DUPLICATE_KEY', 'Duplicate JSON field.', childPath, keyOffset);
        seen.add(key); whitespace();
        if (text[position] !== ':') fail('COLON', 'Expected a colon after JSON field name.', childPath);
        position++;
        const child = value(childPath, depth + 1);
        // Assigning __proto__ normally mutates an object prototype. Define an
        // own property instead: all legal keys remain inert JSON data.
        Object.defineProperty(object, key, {value: child, enumerable: true, writable: true, configurable: true});
        whitespace();
        if (text[position] === '}') { position++; return object; }
        if (text[position] !== ',') fail('DELIMITER', 'Expected a comma or closing delimiter.', path);
        position++; whitespace();
      }
    }
    if (character === '[') {
      position++; whitespace();
      const array = [];
      if (text[position] === ']') { position++; return array; }
      while (true) {
        array.push(value(path + '/' + array.length, depth + 1)); whitespace();
        if (text[position] === ']') { position++; return array; }
        if (text[position] !== ',') fail('DELIMITER', 'Expected a comma or closing delimiter.', path);
        position++; whitespace();
      }
    }
    for (const [literal, result] of [['true', true], ['false', false], ['null', null]]) {
      if (text.startsWith(literal, position)) { position += literal.length; return result; }
    }
    if (character === '-' || character >= '0' && character <= '9') {
      const start = position;
      const match = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/.exec(text.slice(position));
      if (!match) fail('SYNTAX', 'Invalid JSON syntax.', path);
      const literal = match[0]; position += literal.length;
      if (position < text.length && !/[ \t\n\r,}\]]/.test(text[position])) fail('SYNTAX', 'Invalid JSON syntax.', path);
      const result = Number(literal);
      if (!Number.isFinite(result)) fail('NON_FINITE', 'JSON numbers must be finite.', path, start);
      if (result === 0 && /[1-9]/.test(literal.split(/[eE]/)[0])) fail('UNDERFLOW', 'Nonzero JSON number underflow.', path, start);
      // Python's JSON parser preserves integer literals as integers. Reject a
      // bare integer that this browser would silently round before upload.
      if (!/[.eE]/.test(literal) && BigInt(literal) !== BigInt(result)) fail('INTEGER_PRECISION', 'JSON integer loses precision.', path, start);
      return result;
    }
    fail('SYNTAX', 'Invalid JSON syntax.', path);
  }
  const result = value('', 0); whitespace();
  if (position !== text.length) fail('TRAILING_CONTENT', 'Unexpected text after JSON value.');
  return result;
}
