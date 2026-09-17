const PYODIDE_BASE_URL = new URL('/vendor/pyodide/', self.location.origin);
const ENGINE_PACKAGE_URL = new URL('/engine.zip?v=20260916b', self.location.origin);

let enginePromise;

async function loadEngine() {
  const { loadPyodide } = await import(new URL('pyodide.mjs', PYODIDE_BASE_URL).href);
  const pyodide = await loadPyodide({ indexURL: PYODIDE_BASE_URL.href });
  const response = await fetch(ENGINE_PACKAGE_URL, { cache: 'force-cache' });
  if (!response.ok) throw new Error('No se pudo cargar la plantilla de la minuta.');

  pyodide.FS.writeFile('/engine.zip', new Uint8Array(await response.arrayBuffer()));
  pyodide.FS.mkdirTree('/app');
  pyodide.runPython(`
import json
import sys
import zipfile
zipfile.ZipFile('/engine.zip').extractall('/app')
sys.path.insert(0, '/app')
from backend.document_engine import generate_docx
from backend.schema import normalize_payload, validate_payload
`);
  return pyodide;
}

self.onmessage = async ({ data }) => {
  const { id, payload } = data;
  try {
    self.postMessage({ id, progress: 'Cargando motor de documentos…' });
    enginePromise ||= loadEngine();
    const pyodide = await enginePromise;
    self.postMessage({ id, progress: 'Completando la minuta…' });
    pyodide.globals.set('minute_payload_json', JSON.stringify(payload));
    const validation = JSON.parse(pyodide.runPython(`
normalized = normalize_payload(json.loads(minute_payload_json))
json.dumps(validate_payload(normalized, for_generation=True))
`));
    if (Object.keys(validation).length) {
      self.postMessage({ id, fieldErrors: validation });
      return;
    }
    const result = pyodide.runPython('generate_docx(normalized)');
    const bytes = result instanceof Uint8Array ? result : result.toJs();
    result.destroy?.();
    const documentBytes = bytes.slice();
    self.postMessage({ id, documentBytes }, [documentBytes.buffer]);
  } catch (error) {
    console.error('Error al generar la minuta en este equipo:', error);
    self.postMessage({
      id,
      error: error?.message?.split('\n').at(-1) || 'No se pudo generar la minuta. Inténtalo nuevamente.',
    });
  }
};
