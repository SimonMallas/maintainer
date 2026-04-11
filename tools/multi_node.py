import asyncio
import json
from typing import List, Dict

async def check_multi_node_delta(nodes: List[str], config_path: str = 'config.json') -> Dict:
    # Stub for multi-node delta check
    # Compare configs or states across nodes
    deltas = {}
    for node in nodes:
        # Mock fetch from node
        node_config = {'mock': f'config from {node}'}
        # Compare with local
        with open(config_path) as f:
            local = json.load(f)
        delta = {k: node_config.get(k, 'diff') for k in local if local[k] != node_config.get(k)}
        deltas[node] = delta if delta else None
    return {'deltas': deltas, 'issues': [n for n, d in deltas.items() if d]}

# Usage
# asyncio.run(check_multi_node_delta(['node1', 'node2']))