import json
for n in [1, 2]:
    p = f'graphify-out/.graphify_chunk_0{n}.json'
    d = json.loads(open(p, encoding='utf-8').read())
    print(f"chunk {n}: {len(d.get('nodes', []))} nodes, {len(d.get('edges', []))} edges, {len(d.get('hyperedges', []))} hyperedges")
