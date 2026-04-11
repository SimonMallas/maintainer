import hashlib
import json
from flask import Flask, request, jsonify  # assume flask

app = Flask(__name__)

SLSA_HASH = 'expected_slsa_hash'  # stub

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    data = request.json
    # Compute SLSA hash
    payload_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    if payload_hash != SLSA_HASH:
        return jsonify({'error': 'SLSA hash mismatch'}), 400
    # Process webhook
    print('SLSA verified webhook received')
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run()