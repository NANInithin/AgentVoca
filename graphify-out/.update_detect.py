import json
from pathlib import Path

detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text(encoding='utf-8'))

transcripts_path = Path('graphify-out/.graphify_transcripts.json')
if transcripts_path.exists():
    transcripts = json.loads(transcripts_path.read_text(encoding='utf-8'))
    if 'document' not in detect['files']:
        detect['files']['document'] = []
    for t in transcripts:
        abs_t = str(Path(t).resolve())
        if abs_t not in detect['files']['document']:
            detect['files']['document'].append(abs_t)
    detect['total_files'] = sum(len(v) for v in detect['files'].values())

Path('graphify-out/.graphify_detect.json').write_text(
    json.dumps(detect, indent=2, ensure_ascii=False),
    encoding='utf-8',
)
print(f"total_files: {detect['total_files']}")
print(f"document count: {len(detect['files'].get('document', []))}")
