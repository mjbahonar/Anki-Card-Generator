"""Persistent dictionary results and lossless media backups (stdlib SQLite)."""
import hashlib
import json
from pathlib import Path
import sqlite3

from app.lexin_scraper import normalize_headword


def cache_key(name, word, config, audio=False):
    settings = {k: v for k, v in config.data['sources'].get(name, {}).items() if k != 'enabled'}
    if name == 'lexin':
        settings['adapter_revision'] = 2  # Multiple exact entries; legacy keys remain readable.
        settings.setdefault('variant', 'nynorsk' if config.data['language']['source'] == 'nn' else 'bokmal')
        settings['headword_audio'] = bool(audio)
        settings['table_audio'] = bool(settings.get('table_audio', False) and config.data['audio']['enabled']
                                      and config.data.get('cards', {}).get('normal', {}).get('audio', True))
        if settings['variant'] == 'both':
            settings['primary'] = 'nynorsk' if config.data['language']['source'] == 'nn' else 'bokmal'
    elif name == 'google_translate':
        settings['languages'] = config.data['language']
    elif name in ('fastdic', 'cambridge', 'oxford'):
        settings.setdefault('examples_per_definition', 3)
    elif name == 'images':
        settings.setdefault('count', 3)
        settings.setdefault('priority', ['google', 'commons'])
    # The adapter revision protects against reusing output from a changed parser.
    return json.dumps([1, name, normalize_headword(word), settings], sort_keys=True, ensure_ascii=False)


class DictionaryCache:
    def __init__(self, path):
        self.path = Path(path)

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute('PRAGMA foreign_keys = ON')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS results (
                key TEXT PRIMARY KEY, source TEXT NOT NULL, word TEXT NOT NULL,
                content TEXT NOT NULL, sound TEXT NOT NULL, documents TEXT NOT NULL,
                saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS assets (
                digest TEXT PRIMARY KEY, data BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS result_media (
                key TEXT NOT NULL REFERENCES results(key) ON DELETE CASCADE,
                filename TEXT NOT NULL, kind TEXT NOT NULL,
                digest TEXT NOT NULL REFERENCES assets(digest),
                PRIMARY KEY (key, filename, kind));
            ''')
        except Exception:
            db.close()
            raise
        return db

    def delete_word(self, word, source=None):
        """Remove every cached variant for a normalized word; keep local media files."""
        if not self.path.is_file():
            return 0
        normalized = normalize_headword(word)
        db = self.connect()
        try:
            rows = db.execute('SELECT key, word FROM results' + (' WHERE source=?' if source else ''),
                              (source,) if source else ()).fetchall()
            keys = [(key,) for key, stored_word in rows if normalize_headword(stored_word) == normalized]
            with db:
                db.executemany('DELETE FROM results WHERE key=?', keys)
                if keys:
                    db.execute('DELETE FROM assets WHERE NOT EXISTS '
                               '(SELECT 1 FROM result_media WHERE result_media.digest=assets.digest)')
            return len(keys)
        finally:
            db.close()

    def get(self, key, ctx):
        if not self.path.is_file():
            return None
        db = self.connect()
        try:
            row = db.execute('SELECT content, sound, documents FROM results WHERE key=?', (key,)).fetchone()
            if row is None:
                return None
            media = db.execute('SELECT filename, kind, digest, data FROM result_media '
                               'JOIN assets USING(digest) WHERE key=?', (key,)).fetchall()
            if len(media) != db.execute('SELECT COUNT(*) FROM result_media WHERE key=?', (key,)).fetchone()[0]:
                return None
            # Validate the complete backup before restoring anything.
            if any(Path(filename).name != filename or kind not in ('audio', 'image', 'archive')
                   or hashlib.sha256(data).hexdigest() != digest
                   for filename, kind, digest, data in media):
                return None
            for filename, kind, digest, data in media:
                folder = ctx.audio_dir if kind == 'audio' else ctx.images_dir if kind == 'image' else self.path.parent / 'media'
                path = folder / filename
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    folder.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix(path.suffix + '.tmp')
                    temporary.write_bytes(data)
                    temporary.replace(path)
                if kind != 'archive':
                    ctx.register_media(path)
            return row[0], row[1], json.loads(row[2])
        finally:
            db.close()

    def put(self, key, source, word, content, sound, documents, media):
        backups = []
        for path, kind in media:
            data = path.read_bytes()
            backups.append((path.name, kind, hashlib.sha256(data).hexdigest(), data))
        db = self.connect()
        try:
            with db:
                db.execute('INSERT OR REPLACE INTO results(key,source,word,content,sound,documents) VALUES(?,?,?,?,?,?)',
                           (key, source, word, content, sound, json.dumps(documents, ensure_ascii=False)))
                for filename, kind, digest, data in backups:
                    db.execute('INSERT INTO assets VALUES(?,?) ON CONFLICT(digest) DO UPDATE SET data=excluded.data',
                               (digest, data))
                    db.execute('INSERT INTO result_media VALUES(?,?,?,?)', (key, filename, kind, digest))
        finally:
            db.close()
