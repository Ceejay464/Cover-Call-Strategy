"""Verify original archive bytes, unchanged datasets, and executable semantics."""
from pathlib import Path
from hashlib import sha256
import json
from .semantic_verify import fingerprint

ROOT = Path(__file__).resolve().parents[1]
def digest(payload):
    return sha256(payload).hexdigest()
def notebook_signature(path):
    cells=[c for c in json.loads(path.read_text())['cells'] if c['cell_type']=='code']
    return digest(json.dumps([fingerprint(''.join(c['source'])) for c in cells]).encode())
def main():
    manifest=json.loads((ROOT/'docs/original_manifest.json').read_text())
    checked=0
    for item in manifest:
        if item['status']=='removed_cache':continue
        original=ROOT/item.get('archive_path',item['retained_path'])
        if not original.is_file() or digest(original.read_bytes())!=item['sha256']:
            raise SystemExit(f'Original archive/data integrity failed: {original}')
        current=ROOT/item['retained_path']
        if 'semantic_sha256' in item:
            # Compare both files in this runtime: AST dumps can differ by Python version.
            expected = fingerprint(original.read_text()) if 'archive_path' in item else item['semantic_sha256']
            if fingerprint(current.read_text()) != expected:
                raise SystemExit(f'Executable source semantics changed: {current}')
        if 'notebook_semantic_sha256' in item:
            expected = notebook_signature(original) if 'archive_path' in item else item['notebook_semantic_sha256']
            if notebook_signature(current) != expected:
                raise SystemExit(f'Notebook executable semantics changed: {current}')
        checked+=1
    print(f'Verified {checked} original archives/datasets and all translated executable sources.')
if __name__=='__main__':main()
