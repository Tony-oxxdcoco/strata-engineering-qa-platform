import test from 'node:test';
import assert from 'node:assert/strict';
import {parseStrictJSON, StrictJSONError, MAX_JSON_BYTES} from '../web/strict-json.js';

function rejects(text, code, path) {
  assert.throws(() => parseStrictJSON(text), error => {
    assert.ok(error instanceof StrictJSONError);
    assert.equal(error.code, code);
    if (path) assert.equal(error.path, path);
    assert.ok(error.line > 0 && error.column > 0 && error.offset >= 0);
    return true;
  });
}

test('valid JSON keeps strings, arrays, booleans, null, numbers and insertion order', () => {
  const raw = '{"z":null,"a":[true,false,0,-0,1.25,1e3,"kN","原字段"],"nested":{"x":2}}';
  assert.deepEqual(parseStrictJSON(raw), JSON.parse(raw));
  assert.deepEqual(Object.keys(parseStrictJSON(raw)), ['z','a','nested']);
  assert.equal(Object.is(parseStrictJSON(raw).a[3], -0), true);
});

test('decoded duplicate keys are rejected before last-field overwrite', () => {
  rejects('{"Mass":1,"Mass":0}', 'DUPLICATE_KEY', '/Mass');
  rejects('{"Mass":1,"\\u004Dass":0}', 'DUPLICATE_KEY', '/Mass');
  rejects('{"a/b~c":{"x":1,"\\u0078":2}}', 'DUPLICATE_KEY', '/a~1b~0c/x');
  rejects('[{"value":1,"value":2}]', 'DUPLICATE_KEY', '/0/value');
});

test('the same field name in separate objects is legitimate data', () => {
  assert.deepEqual(parseStrictJSON('[{"id":"A"},{"id":"B"}]'), [{id:'A'},{id:'B'}]);
});

test('nonzero underflow cannot turn raw configuration into a passing zero', () => {
  for (const literal of ['1e-999','-1e-999','0.0001E-999','1.0000e-999']) {
    rejects(`{"rules":[{"factor":${literal}}]}`, 'UNDERFLOW', '/rules/0/factor');
  }
  assert.equal(parseStrictJSON('0e-999'), 0);
  assert.equal(Object.is(parseStrictJSON('-0e-999'), -0), true);
  assert.equal(parseStrictJSON('5e-324'), Number.MIN_VALUE);
});

test('overflow and non-JSON constants never become null or other values', () => {
  rejects('{"limit":1e999}', 'NON_FINITE', '/limit');
  rejects('{"limit":-1e999}', 'NON_FINITE', '/limit');
  for (const raw of ['NaN','Infinity','-Infinity','undefined']) rejects(raw, 'SYNTAX');
});

test('nonrepresentable integer cannot be rounded before sending to Python', () => {
  rejects('{"record":9007199254740993}', 'INTEGER_PRECISION', '/record');
  rejects('-9007199254740993', 'INTEGER_PRECISION', '/');
  assert.equal(parseStrictJSON('9007199254740992'), 9007199254740992);
  assert.equal(parseStrictJSON('10000000000000000'), 10000000000000000);
  assert.equal(parseStrictJSON('1e20'), 1e20);
});

test('depth matches the backend 32-level gate with explicit paths', () => {
  assert.doesNotThrow(() => parseStrictJSON('['.repeat(32)+'0'+']'.repeat(32)));
  rejects('['.repeat(33)+'0'+']'.repeat(33), 'DEPTH_LIMIT');
  assert.throws(() => parseStrictJSON('{"a":{"b":0}}', {maxDepth:1}), e=>e.code==='DEPTH_LIMIT'&&e.path==='/a/b');
});

test('UTF-8 byte bound applies before parsing, including multibyte text', () => {
  assert.equal(parseStrictJSON('"中"', {maxBytes:5}), '中');
  assert.throws(() => parseStrictJSON('"中"', {maxBytes:4}), e=>e.code==='SIZE_LIMIT');
  rejects(' '.repeat(MAX_JSON_BYTES+1), 'SIZE_LIMIT');
});

test('configuration cannot disable size or nesting guards', () => {
  for (const options of [{maxBytes:Infinity},{maxBytes:0},{maxDepth:33},{maxDepth:-1},{maxBytes:10.5}]) {
    assert.throws(() => parseStrictJSON('{}',options), TypeError);
  }
});

test('special object keys stay own JSON properties and never pollute prototypes', () => {
  const raw='{"__proto__":{"polluted":true},"constructor":{"prototype":{"polluted":true}},"prototype":7}';
  const value=parseStrictJSON(raw);
  assert.equal(Object.getPrototypeOf(value), Object.prototype);
  assert.equal(Object.hasOwn(value,'__proto__'), true);
  assert.equal(value.__proto__.polluted, true);
  assert.equal({}.polluted, undefined);
  assert.equal(JSON.stringify(value), raw);
});

test('valid escapes, Unicode pairs, literal slashes and braces are preserved', () => {
  const raw='{"a":"\\\"{}[],:\\\\\\/\\b\\f\\n\\r\\t\\u4e2d\\ud83d\\ude00"}';
  assert.deepEqual(parseStrictJSON(raw), JSON.parse(raw));
  assert.deepEqual(parseStrictJSON('{"\\u002f":1,"~":2}'), {'/':1,'~':2});
});

test('lone Unicode surrogates cannot become replacement characters in evidence', () => {
  rejects('"\\ud800"', 'UNICODE');
  rejects('"\\udc00"', 'UNICODE');
  rejects('"\ud800"', 'UNICODE');
});

test('malformed object, array, literal and number forms are rejected', () => {
  for (const raw of ['', ' ', '{', '[', '{"x":}', '[1,]', '{"x":1,}', '[,1]', '01', '+1', '.5', '1.', '1e', '0x10', 'truex', '[false true]']) {
    assert.throws(() => parseStrictJSON(raw), StrictJSONError, raw);
  }
  rejects('"\\x41"', 'STRING_ESCAPE');
  rejects('"\\uZZZZ"', 'STRING_ESCAPE');
  rejects('"unfinished', 'UNTERMINATED_STRING');
  rejects('"raw\nline"', 'SYNTAX');
  rejects('null false', 'TRAILING_CONTENT');
});

test('duplicate error retains decoded field path and original second-field location', () => {
  const raw='{\n  "nested": {\n    "q":1,\n    "\\u0071":2\n  }\n}';
  assert.throws(() => parseStrictJSON(raw), error => {
    assert.equal(error.path,'/nested/q');
    assert.equal(error.line,4);assert.equal(error.column,5);
    assert.equal(raw.slice(error.offset,error.offset+8),'"\\u0071"');
    assert.match(error.message,/Strict JSON error: Duplicate JSON field\. at line 4, column 5, path \/nested\/q\./);
    return true;
  });
});

test('top-level JSON types remain unchanged and parsing never executes source text', () => {
  for (const raw of ['null','true','false','123','-0.5','"__import__(os)"','[]','{}']) assert.deepEqual(parseStrictJSON(raw),JSON.parse(raw));
  rejects(null,'INPUT_TYPE');rejects({value:1},'INPUT_TYPE');
});
