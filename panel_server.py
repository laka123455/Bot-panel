#!/usr/bin/env python3
"""Local-only personal bot panel backend. Only runs scripts in ~/myhost/bots."""
from flask import Flask, jsonify, request
from pathlib import Path
import subprocess, sys, time, threading

ROOT = Path.home() / 'myhost'
BOTS = ROOT / 'bots'
LOGS = ROOT / 'logs'
BOTS.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)
TOKEN = 'change-this-local-token'  # Must match app/src/main/assets/index.html
app = Flask(__name__)
procs = {}
lock = threading.Lock()

def valid_name(name):
    return isinstance(name, str) and name.endswith('.py') and Path(name).name == name and name not in ('.', '..')

def get_script(name):
    if not valid_name(name):
        return None
    p = (BOTS / name).resolve()
    if p.parent != BOTS.resolve() or not p.is_file():
        return None
    return p

def running(name):
    p = procs.get(name)
    return bool(p and p.poll() is None)

@app.before_request
def protect():
    if request.method == 'OPTIONS' or request.path == '/health':
        return None
    if request.headers.get('X-Panel-Token') != TOKEN:
        return jsonify(error='Invalid panel token'), 401
    # Allow the APK's local file origin; no cookies or credentials are used.
    origin = request.headers.get('Origin', '*')
    request.environ['panel_origin'] = origin

@app.after_request
def cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Panel-Token'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

@app.route('/api/<path:unused>', methods=['OPTIONS'])
def options(unused):
    return ('', 204)

@app.get('/health')
def health():
    return jsonify(ok=True, message='Bot Panel backend ready')

@app.get('/api/bots')
def bots():
    result = []
    for p in sorted(BOTS.glob('*.py')):
        result.append({'name': p.name, 'running': running(p.name)})
    return jsonify(bots=result)

@app.post('/api/bot/<name>/start')
def start(name):
    script = get_script(name)
    if script is None:
        return jsonify(error='Script not found. Put a .py file in ~/myhost/bots.'), 404
    with lock:
        if running(name):
            return jsonify(ok=True, message='Already running')
        log_path = LOGS / (name + '.log')
        log = open(log_path, 'ab', buffering=0)
        log.write(('\n\n--- START %s ---\n' % time.strftime('%Y-%m-%d %H:%M:%S')).encode())
        try:
            p = subprocess.Popen([sys.executable, '-u', str(script)], cwd=str(BOTS), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            procs[name] = p
        finally:
            log.close()
    return jsonify(ok=True, message='Started')

@app.post('/api/bot/<name>/stop')
def stop(name):
    if not valid_name(name):
        return jsonify(error='Invalid script name'), 400
    with lock:
        p = procs.get(name)
        if p and p.poll() is None:
            p.terminate()
            try: p.wait(timeout=4)
            except subprocess.TimeoutExpired: p.kill()
    return jsonify(ok=True, message='Stopped')

@app.post('/api/bot/<name>/restart')
def restart(name):
    script = get_script(name)
    if script is None:
        return jsonify(error='Script not found'), 404
    p = procs.get(name)
    if p and p.poll() is None:
        p.terminate()
        try: p.wait(timeout=4)
        except subprocess.TimeoutExpired: p.kill()
    return start(name)

@app.get('/api/bot/<name>/logs')
def logs(name):
    if not valid_name(name):
        return jsonify(error='Invalid script name'), 400
    p = LOGS / (name + '.log')
    if not p.exists():
        return jsonify(logs='No logs yet.')
    try:
        data = p.read_text(errors='replace')[-12000:]
    except OSError as e:
        return jsonify(error=str(e)), 500
    return jsonify(logs=data)

if __name__ == '__main__':
    print('Bot Panel backend listening on http://127.0.0.1:8765')
    app.run(host='127.0.0.1', port=8765, debug=False, threaded=True)
