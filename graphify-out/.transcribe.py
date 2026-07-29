import json, os, sys
from pathlib import Path
from graphify.transcribe import transcribe_all

detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text(encoding="utf-8"))
video_files = detect.get('files', {}).get('video', [])
prompt = os.environ.get('GRAPHIFY_WHISPER_PROMPT', 'Use proper punctuation and paragraph breaks.')

transcript_paths = transcribe_all(video_files, initial_prompt=prompt)
Path('graphify-out/.graphify_transcripts.json').write_text(json.dumps(transcript_paths, ensure_ascii=False), encoding="utf-8")
print(f'Transcribed {len(transcript_paths)} file(s)', file=sys.stderr)
