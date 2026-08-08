import re
from pathlib import Path
root = Path(__file__).resolve().parent.parent
patterns = [
    (re.compile(r'AKIA[0-9A-Z]{16}'), 'AWS_ACCESS_KEY_ID'),
    (re.compile(r'(?i)BREETH_API_KEY\s*=\s*[^\s#]+'), 'BREETH_API_KEY-like'),
    (re.compile(r'(?i)OPENAI_API_KEY\s*=\s*[^\s#]+'), 'OPENAI_API_KEY-like'),
    (re.compile(r'(?i)SECRET\s*[:=]\s*\S+'), 'generic SECRET-like'),
]
found = []
for p in root.rglob('*'):
    if p.is_file():
        if 'venv' in p.parts or '.git' in p.parts:
            continue
        if p.suffix.lower() not in ['.py', '.md', '.toml', '.env', '.json', '.yaml', '.yml']:
            continue
        try:
            text = p.read_text(errors='ignore')
        except Exception:
            continue
        for pat, name in patterns:
            if pat.search(text):
                found.append((str(p.relative_to(root)), name))
                break
print('secrets_found', len(found))
for path, kind in found:
    print(kind, path)
