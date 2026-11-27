"""Local settings GUI: a small HTTP server on 127.0.0.1 plus a browser page.

Only the Python standard library and tomlkit are needed. Runs, checks and cache
maintenance start ``main.py`` as a separate process, exactly like the command
line, so every run reads config.toml from disk and nothing about running
cards changes. The page talks to the server with a random per-session token,
and requests from other hosts or origins are refused.
"""
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from urllib.parse import parse_qs
import webbrowser

from app.app_config import ConfigError
from app.gui import config_doc, i18n

STATIC = Path(__file__).with_name('static')
STATIC_FILES = {'index.html': 'text/html', 'app.css': 'text/css', 'app.js': 'text/javascript'}
# Persian interface font (OFL), shared with the cards: fonts/ next to main.py.
FONT_FILES = {'Vazirmatn.ttf': '_Vazirmatn.ttf', 'Vazirmatn-Bold.ttf': '_Vazirmatn-Bold.ttf'}
PROGRESS = re.compile(r'^\[(\d+)/(\d+)\] (.*)$')
MAX_LINES = 20000


class Job:
    def __init__(self, kind, process):
        self.kind = kind
        self.process = process
        self.lines = []
        self.returncode = None
        self.progress = None
        self.stopping = False
        self.stop_file = None
        self.started = time.time()

    def read(self):
        for line in self.process.stdout:
            line = line.rstrip('\r\n')
            match = PROGRESS.match(line.strip())
            if match:
                self.progress = {'current': int(match[1]), 'total': int(match[2]), 'word': match[3]}
            self.lines.append(line)
            if len(self.lines) > MAX_LINES:
                del self.lines[:1000]
        self.returncode = self.process.wait()
        if self.stop_file is not None:
            self.stop_file.unlink(missing_ok=True)

    @property
    def running(self):
        return self.returncode is None


class GuiApp:
    def __init__(self, config_path, launcher):
        self.config_path = Path(config_path).resolve()
        self.launcher = Path(launcher).resolve()
        self.token = secrets.token_urlsafe(24)
        self.job = None
        self.lock = threading.Lock()
        self.dialog_lock = threading.Lock()

    # Tasks -----------------------------------------------------------------
    def start(self, kind, extra=()):
        with self.lock:
            if self.job and self.job.running:
                raise RuntimeError('busy')
            command = [sys.executable, '-u', str(self.launcher), '--config', str(self.config_path), *extra]
            # Stop creates this file; main.py finishes the current step, saves and exits (see StopRequest).
            stop_file = Path(tempfile.gettempdir()) / f'anki-card-generator-stop-{self.token[:12]}-{time.time_ns()}'
            env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1',
                       ANKI_CARD_GENERATOR_STOP_FILE=str(stop_file))
            flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            process = subprocess.Popen(command, cwd=self.launcher.parent, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                       encoding='utf-8', errors='replace', env=env, creationflags=flags,
                                       start_new_session=os.name != 'nt')
            self.job = Job(kind, process)
            self.job.stop_file = stop_file
            threading.Thread(target=self.job.read, daemon=True).start()
            return self.job

    def stop(self):
        job = self.job
        if not job or not job.running:
            return False
        if job.stopping:  # Second press: end it now.
            job.process.kill()
            return True
        job.stopping = True
        if job.stop_file is not None:
            # A file, not a console signal: a signal would also reach the browser and could hang the run.
            job.stop_file.write_text('stop', encoding='utf-8')
        else:
            # Jobs started without a stop file (for example by projects that subclass GuiApp): Ctrl+Break / SIGINT.
            job.process.send_signal(signal.CTRL_BREAK_EVENT if os.name == 'nt' else signal.SIGINT)
        return True

    def job_state(self, since=0):
        job = self.job
        if not job:
            return {'kind': None, 'running': False, 'lines': [], 'next': 0}
        lines = job.lines
        since = max(0, min(since, len(lines)))
        return {'kind': job.kind, 'running': job.running, 'returncode': job.returncode,
                'stopping': job.stopping, 'progress': job.progress,
                'lines': lines[since:], 'next': len(lines)}

    # Settings --------------------------------------------------------------
    def _settings(self):
        with self.config_path.open('rb') as stream:
            return tomllib.load(stream)

    def cache(self):
        from app.dictionary_cache import DictionaryCache
        cache = self._settings().get('dictionary_cache', {})
        return DictionaryCache(self.resolve(cache.get('path', 'Cache/dictionaries.sqlite3')))

    def resolve(self, value):
        path = Path(str(value)).expanduser()
        return path if path.is_absolute() else (self.config_path.parent / path)

    def files(self, check=None):
        state = {'input_files': self.input_files(), 'style_files': self.style_files()}
        if check is not None:
            state['exists'] = bool(check.strip()) and self.resolve(check.strip()).is_file()
        return state

    def style_files(self):
        folder = self.config_path.parent
        return sorted(p.relative_to(folder).as_posix() for p in folder.glob('Styles/*.css'))

    def browse(self, kind, current=''):
        """Native "Open file" dialog on this computer; returns a path relative to config.toml when possible."""
        import tkinter as tk
        from tkinter import filedialog
        types = ([('Excel workbooks', '*.xlsx *.xlsm *.xls'), ('All files', '*.*')] if kind == 'input'
                 else [('Style sheets', '*.css'), ('All files', '*.*')])
        start = self.resolve(current).parent if current else self.config_path.parent
        if not start.is_dir():
            start = self.config_path.parent
        with self.dialog_lock:
            root = tk.Tk()
            try:
                root.withdraw()
                root.attributes('-topmost', True)
                chosen = filedialog.askopenfilename(parent=root, initialdir=str(start), filetypes=types,
                                                    title='Choose a workbook' if kind == 'input' else 'Choose a style sheet')
            finally:
                root.destroy()
        if not chosen:
            return None
        path = Path(chosen).resolve()
        try:
            return path.relative_to(self.config_path.parent).as_posix()
        except ValueError:
            return path.as_posix()

    def input_files(self):
        folder = self.config_path.parent
        found = []
        for pattern in ('*.xlsx', '*.xlsm', '*.xls', 'Input Excels/*.xlsx', 'Input Excels/*.xls'):
            found.extend(p.relative_to(folder).as_posix() for p in folder.glob(pattern)
                         if not p.name.startswith('~$'))
        return sorted(set(found), key=str.lower)

    def state(self, language):
        from app import __version__
        from app.sources import SOURCE_SPECS
        return {'strings': i18n.strings(language), 'languages': i18n.languages(),
                'config_path': str(self.config_path), 'app_version': __version__,
                'schema': config_doc.describe(self.config_path), 'input_files': self.input_files(),
                'style_files': self.style_files(),
                'cache_sources': list(SOURCE_SPECS), 'job': self.job_state()}

    def open_folder(self, what):
        settings = self._settings()
        folder = self.resolve(settings['output']['directory']) if what == 'output' else self.config_path.parent
        folder.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt':
            os.startfile(folder)  # noqa: S606 - opens Explorer on a local folder
        else:
            subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(folder)])


def make_handler(app, port_holder):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'AnkiCardGeneratorGUI'

        def log_message(self, *args):  # Keep the terminal for useful messages.
            pass

        def _send(self, status, body, content_type='application/json'):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'max-age=86400' if content_type == 'font/ttf' else 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy',
                             "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:")
            self.end_headers()
            self.wfile.write(data)

        def _allowed_host(self):
            port = port_holder['port']
            host = self.headers.get('Host', '')
            origin = self.headers.get('Origin')
            hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
            return host in hosts and (origin is None or origin in {'http://' + h for h in hosts})

        def _authorized(self):
            return self._allowed_host() and secrets.compare_digest(
                self.headers.get('X-GUI-Token', ''), app.token)

        def _body(self):
            length = int(self.headers.get('Content-Length') or 0)
            if length > 2_000_000:
                raise ValueError('Request too large')
            return json.loads(self.rfile.read(length) or b'{}')

        def do_GET(self):
            if not self._allowed_host():
                return self._send(HTTPStatus.FORBIDDEN, {'error': 'Forbidden host'})
            route, _, query = self.path.partition('?')
            if route.startswith('/fonts/'):
                source = FONT_FILES.get(route[len('/fonts/'):])
                path = app.launcher.parent / 'fonts' / source if source else None
                if not path or not path.is_file():
                    return self._send(HTTPStatus.NOT_FOUND, {'error': 'Not found'})
                return self._send(HTTPStatus.OK, path.read_bytes(), 'font/ttf')
            if route == '/' or route.startswith('/static/'):
                name = 'index.html' if route == '/' else route[len('/static/'):]
                if name not in STATIC_FILES:
                    return self._send(HTTPStatus.NOT_FOUND, {'error': 'Not found'})
                return self._send(HTTPStatus.OK, (STATIC / name).read_bytes(), STATIC_FILES[name])
            if not self._authorized():
                return self._send(HTTPStatus.FORBIDDEN, {'error': 'Missing or wrong session token'})
            params = {key: values[0] for key, values in parse_qs(query).items()}
            try:
                if route == '/api/state':
                    return self._send(HTTPStatus.OK, app.state(params.get('lang')))
                if route == '/api/files':
                    return self._send(HTTPStatus.OK, app.files(params.get('check')))
                if route == '/api/db/stats':
                    return self._send(HTTPStatus.OK, app.cache().stats())
                if route == '/api/db/search':
                    status = params.get('status') or None
                    if status not in (None, 'found', 'indirect', 'offline', 'not_found'):
                        raise ValueError('Unknown status filter')
                    return self._send(HTTPStatus.OK, app.cache().search(
                        params.get('q', ''), params.get('source') or None, status,
                        limit=min(int(params.get('limit', 100)), 500), offset=max(0, int(params.get('offset', 0)))))
                if route == '/api/db/entry':
                    entry = app.cache().entry(params.get('key', ''))
                    return self._send(HTTPStatus.OK if entry else HTTPStatus.NOT_FOUND, entry or {'error': 'Not found'})
                if route == '/api/job':
                    return self._send(HTTPStatus.OK, app.job_state(int(params.get('since', 0))))
            except (OSError, ValueError, ConfigError, sqlite3.Error) as exc:
                return self._send(HTTPStatus.BAD_REQUEST, {'error': str(exc)})
            return self._send(HTTPStatus.NOT_FOUND, {'error': 'Not found'})

        def do_POST(self):
            if not self._authorized():
                # Read the unwanted body first: replying with it unread can reset the connection on Windows.
                length = int(self.headers.get('Content-Length') or 0)
                if 0 < length <= 2_000_000:
                    self.rfile.read(length)
                return self._send(HTTPStatus.FORBIDDEN, {'error': 'Missing or wrong session token'})
            try:
                body = self._body()
                if self.path == '/api/save':
                    if app.job and app.job.running:
                        return self._send(HTTPStatus.CONFLICT, {'error': 'busy'})
                    new_version, warning = config_doc.save(
                        app.config_path, body.get('changes', []), body.get('sources_order'), body.get('version'))
                    return self._send(HTTPStatus.OK, {'version': new_version, 'warning': warning})
                if self.path == '/api/run':
                    kind = body.get('kind')
                    if kind == 'run':
                        extra = []
                    elif kind == 'check':
                        extra = ['--check']
                    elif kind == 'refresh_word':
                        from app.sources import SOURCE_SPECS
                        word, source = str(body.get('word') or '').strip(), body.get('source')
                        if not word or '\n' in word:
                            raise ValueError('Word must not be blank')
                        if source is not None and source not in SOURCE_SPECS:
                            raise ValueError('Unknown dictionary')
                        extra = ['--refresh-word=' + word] + (['--source', source] if source else [])
                    elif kind == 'upgrade_cache':
                        extra = ['--upgrade-cache']
                    elif kind == 'clear_cache':
                        from app.sources import SOURCE_SPECS
                        source = body.get('source')
                        if source not in SOURCE_SPECS:
                            raise ValueError('Unknown dictionary')
                        extra = ['--clear-source-cache', source]
                    else:
                        raise ValueError('Unknown task')
                    app.start(kind, extra)
                    return self._send(HTTPStatus.OK, app.job_state())
                if self.path.startswith('/api/db/'):
                    if app.job and app.job.running:  # A run writes to the same database.
                        return self._send(HTTPStatus.CONFLICT, {'error': 'busy'})
                    cache = app.cache()
                    if self.path == '/api/db/delete':
                        keys = body.get('keys')
                        if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
                            raise ValueError('keys must be a list')
                        return self._send(HTTPStatus.OK, {'removed': cache.delete_keys(keys)})
                    if self.path == '/api/db/delete_matching':
                        status = body.get('status') or None
                        if status not in (None, 'found', 'indirect', 'offline', 'not_found'):
                            raise ValueError('Unknown status filter')
                        return self._send(HTTPStatus.OK, {'removed': cache.delete_matching(
                            str(body.get('q') or ''), body.get('source') or None, status)})
                    if self.path == '/api/db/forget_not_found':
                        return self._send(HTTPStatus.OK, {'removed': cache.delete_not_found(body.get('source') or None)})
                    if self.path == '/api/db/compact':
                        before, after = cache.compact()
                        return self._send(HTTPStatus.OK, {'before': before, 'after': after})
                if self.path == '/api/stop':
                    return self._send(HTTPStatus.OK, {'stopped': app.stop()})
                if self.path == '/api/browse':
                    kind = body.get('kind')
                    if kind not in ('input', 'style'):
                        raise ValueError('Unknown file kind')
                    return self._send(HTTPStatus.OK, {'path': app.browse(kind, str(body.get('current') or ''))})
                if self.path == '/api/open':
                    app.open_folder(body.get('what'))
                    return self._send(HTTPStatus.OK, {})
            except config_doc.ConflictError:
                return self._send(HTTPStatus.CONFLICT, {'error': 'conflict'})
            except RuntimeError as exc:
                return self._send(HTTPStatus.CONFLICT, {'error': str(exc)})
            except (OSError, ValueError, KeyError, ConfigError, sqlite3.Error) as exc:
                return self._send(HTTPStatus.BAD_REQUEST, {'error': str(exc)})
            return self._send(HTTPStatus.NOT_FOUND, {'error': 'Not found'})

    return Handler


def create_server(config_path, launcher, port=0):
    app = GuiApp(config_path, launcher)
    holder = {'port': port}
    server = ThreadingHTTPServer(('127.0.0.1', port), make_handler(app, holder))
    holder['port'] = server.server_address[1]
    server.daemon_threads = True
    return server, app


def serve(config_path, launcher, port=0, open_browser=True):
    server, app = create_server(config_path, launcher, port)
    url = f'http://127.0.0.1:{server.server_address[1]}/#token={app.token}'
    print(f'Settings GUI: {url}\nKeep this window open while you use the GUI. Press Ctrl+C here to close it.', flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if app.job and app.job.running:
            app.job.process.kill()
        server.server_close()
    return 0
