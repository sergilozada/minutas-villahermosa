import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { loadPyodide } from '../static/vendor/pyodide/pyodide.mjs';

const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
const payload = JSON.parse(Buffer.concat(chunks).toString('utf8'));

const pyodide = await loadPyodide({
  indexURL: fileURLToPath(new URL('../static/vendor/pyodide/', import.meta.url)),
});
pyodide.FS.writeFile('/engine.zip', readFileSync(new URL('../static/engine.zip', import.meta.url)));
pyodide.FS.mkdirTree('/app');
pyodide.runPython(`
import io
import json
import sys
import zipfile
zipfile.ZipFile('/engine.zip').extractall('/app')
sys.path.insert(0, '/app')
from backend.document_engine import generate_docx
from backend.schema import normalize_payload, validate_payload
`);
pyodide.globals.set('minute_payload_json', JSON.stringify(payload));
const validation = JSON.parse(pyodide.runPython(`
normalized = normalize_payload(json.loads(minute_payload_json))
json.dumps(validate_payload(normalized, for_generation=True))
`));
assert.deepEqual(validation, {});

const document = pyodide.runPython('generate_docx(normalized)');
const bytes = document instanceof Uint8Array ? document : document.toJs();
assert.ok(bytes.byteLength > 40_000);
const validZip = pyodide.runPython(`
with zipfile.ZipFile(io.BytesIO(generate_docx(normalized))) as generated:
    zip_ok = generated.testzip() is None and 'word/document.xml' in generated.namelist()
zip_ok
`);
assert.equal(validZip, true);
document.destroy?.();
console.log(`Browser engine generated a valid ${bytes.byteLength}-byte DOCX`);
