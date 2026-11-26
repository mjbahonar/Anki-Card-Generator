"""Persistent dictionary results and lossless media backups (stdlib SQLite)."""
import hashlib
import html
import json
import re
from pathlib import Path
import sqlite3

from app.lexin_scraper import normalize_headword


def cache_key(name, word, config, audio=False):
    settings = {k: v for k, v in config.data['sources'].get(name, {}).items() if k != 'enabled'}
    if name == 'lexin':
        settings['adapter_revision'] = 2  # Multiple exact entries; legacy keys serve entries = 1 only.
        if settings.get('entries', 2) == 2:
            settings.pop('entries', None)  # Revision 2 always inspected two results.
        # form_entries only decides "not found" results, which record it themselves; found results
        # do not depend on it, so it must not change their key (5.8.0-5.9.0 included it by mistake).
        settings.pop('form_entries', None)
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
        if 'bing' in settings['priority']:
            settings['bing_query'] = 'clipart'  # Bing searches "<word> clipart"; earlier plain-word results are not reused.
    # The adapter revision protects against reusing output from a changed parser.
    return json.dumps([1, name, normalize_headword(word), settings], sort_keys=True, ensure_ascii=False)


# A result found through an inflected form ("gikk → gå") carries this note in its content: an
# indirect translation. Statuses: found (direct), indirect, not_found.
INDIRECT_MARK = '%lexin-form-note%'
FORM_NOTE = re.compile(r'lexin-form-note">.*?→ <b>(.*?)</b>', re.S)


def indirect_bases(content):
    """Base words of an indirect result, e.g. ['gå'] for gikk; [] for a direct result."""
    return list(dict.fromkeys(html.unescape(m) for m in FORM_NOTE.findall(content or '')))


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

    # Browsing and maintenance (settings GUI). A result with empty content records that the
    # dictionary answered and the word is definitely not in it; later runs skip the lookup.

    def stats(self):
        """Overview: file size, results per source (found / not found) and stored media."""
        info = {'path': str(self.path), 'exists': self.path.is_file(), 'file_bytes': 0, 'sources': [],
                'media': [], 'results': 0, 'not_found': 0, 'indirect': 0, 'words': 0, 'media_bytes': 0, 'text_bytes': 0,
                'oldest': None, 'newest': None}
        if not info['exists']:
            return info
        info['file_bytes'] = self.path.stat().st_size
        db = self.connect()
        try:
            for source, total, missing, indirect, text, oldest, newest in db.execute(
                    "SELECT source, COUNT(*), SUM(content=''), SUM(content LIKE ?), SUM(LENGTH(content)+LENGTH(documents)), "
                    "MIN(saved_at), MAX(saved_at) FROM results GROUP BY source ORDER BY COUNT(*) DESC", (INDIRECT_MARK,)):
                info['sources'].append({'source': source, 'results': total, 'not_found': missing or 0,
                                        'indirect': indirect or 0, 'text_bytes': text or 0,
                                        'oldest': oldest, 'newest': newest})
            info['results'] = sum(s['results'] for s in info['sources'])
            info['not_found'] = sum(s['not_found'] for s in info['sources'])
            info['indirect'] = sum(s['indirect'] for s in info['sources'])
            info['text_bytes'] = sum(s['text_bytes'] for s in info['sources'])
            info['words'] = len({normalize_headword(w) for (w,) in db.execute('SELECT word FROM results')})
            dates = [s for s in info['sources'] if s['oldest']]
            if dates:
                info['oldest'] = min(s['oldest'] for s in dates)
                info['newest'] = max(s['newest'] for s in dates)
            for kind, files, size in db.execute(
                    'SELECT kind, COUNT(*), SUM(LENGTH(data)) FROM (SELECT DISTINCT m.kind, a.digest, a.data '
                    'FROM result_media m JOIN assets a USING(digest)) GROUP BY kind ORDER BY kind'):
                info['media'].append({'kind': kind, 'files': files, 'bytes': size or 0})
            info['media_bytes'] = db.execute('SELECT COALESCE(SUM(LENGTH(data)), 0) FROM assets').fetchone()[0]
        finally:
            db.close()
        return info

    @staticmethod
    def _filter(query='', source=None, status=None):
        """SQL WHERE clause (on alias r) for a word search, dictionary and found/not-found status."""
        where, args = [], []
        if query.strip():
            where.append("r.word LIKE ? ESCAPE '!'")
            args.append('%' + query.strip().replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%')
        if source:
            where.append('r.source = ?')
            args.append(source)
        if status == 'found':  # Direct: the word itself is a headword.
            where.append("r.content != '' AND r.content NOT LIKE ?")
            args.append(INDIRECT_MARK)
        elif status == 'indirect':  # Through an inflected form (gikk → gå).
            where.append('r.content LIKE ?')
            args.append(INDIRECT_MARK)
        elif status == 'not_found':
            where.append("r.content = ''")
        return (' WHERE ' + ' AND '.join(where)) if where else '', args

    def search(self, query='', source=None, status=None, limit=100, offset=0):
        """Cached results whose word contains query; status is None, 'found', 'indirect' or 'not_found'."""
        if not self.path.is_file():
            return {'total': 0, 'rows': []}
        clause, args = self._filter(query, source, status)
        db = self.connect()
        try:
            total = db.execute('SELECT COUNT(*) FROM results r' + clause, args).fetchone()[0]
            rows = db.execute(
                'SELECT r.key, r.word, r.source, r.content = \'\', r.saved_at, LENGTH(r.content) + LENGTH(r.documents), '
                'CASE WHEN r.content LIKE \'%lexin-form-note%\' THEN r.content ELSE \'\' END, '
                '(SELECT COUNT(*) FROM result_media m WHERE m.key = r.key), '
                '(SELECT COALESCE(SUM(LENGTH(a.data)), 0) FROM result_media m JOIN assets a USING(digest) WHERE m.key = r.key) '
                'FROM results r' + clause + ' ORDER BY r.word COLLATE NOCASE, r.source LIMIT ? OFFSET ?', args + [int(limit), int(offset)]).fetchall()
        finally:
            db.close()
        return {'total': total, 'rows': [
            {'key': key, 'word': word, 'source': src, 'not_found': bool(missing), 'saved_at': saved,
             'indirect': indirect_bases(note), 'text_bytes': text or 0, 'media_files': files, 'media_bytes': size}
            for key, word, src, missing, saved, text, note, files, size in rows]}

    def entry(self, key):
        """One cached result: its card HTML and the media file names it restores."""
        if not self.path.is_file():
            return None
        db = self.connect()
        try:
            row = db.execute('SELECT word, source, content, sound, saved_at FROM results WHERE key=?', (key,)).fetchone()
            if row is None:
                return None
            media = db.execute('SELECT m.filename, m.kind, LENGTH(a.data) FROM result_media m JOIN assets a USING(digest) '
                               'WHERE m.key=? ORDER BY m.kind, m.filename', (key,)).fetchall()
        finally:
            db.close()
        word, source, content, sound, saved = row
        try:
            settings = json.loads(key)[3]
        except (ValueError, IndexError, TypeError):
            settings = {}
        return {'key': key, 'word': word, 'source': source, 'content': content, 'sound': sound, 'saved_at': saved,
                'not_found': not content, 'settings': settings,
                'media': [{'filename': f, 'kind': k, 'bytes': b} for f, k, b in media]}

    def delete_keys(self, keys):
        """Remove the given results and backups no other result uses; local files stay."""
        if not self.path.is_file() or not keys:
            return 0
        db = self.connect()
        try:
            with db:
                count = sum(db.execute('DELETE FROM results WHERE key=?', (key,)).rowcount for key in keys)
                db.execute('DELETE FROM assets WHERE NOT EXISTS '
                           '(SELECT 1 FROM result_media WHERE result_media.digest=assets.digest)')
            return count
        finally:
            db.close()

    def delete_matching(self, query='', source=None, status=None):
        """Remove every result a search would list (same filters); unused backups go too."""
        if not self.path.is_file():
            return 0
        clause, args = self._filter(query, source, status)
        db = self.connect()
        try:
            with db:
                count = db.execute('DELETE FROM results WHERE key IN (SELECT r.key FROM results r' + clause + ')',
                                   args).rowcount
                db.execute('DELETE FROM assets WHERE NOT EXISTS '
                           '(SELECT 1 FROM result_media WHERE result_media.digest=assets.digest)')
            return count
        finally:
            db.close()

    def delete_not_found(self, source=None):
        """Forget "not in this dictionary" results so those words are looked up again."""
        if not self.path.is_file():
            return 0
        db = self.connect()
        try:
            with db:
                return db.execute("DELETE FROM results WHERE content = ''" + (' AND source = ?' if source else ''),
                                  (source,) if source else ()).rowcount
        finally:
            db.close()

    def compact(self):
        """Rebuild the file so space from deleted results is returned to the disk."""
        if not self.path.is_file():
            return 0, 0
        before = self.path.stat().st_size
        db = self.connect()
        try:
            db.execute('VACUUM')
        finally:
            db.close()
        return before, self.path.stat().st_size

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

    def delete_source(self, source):
        """Remove every cached result of one source, its unused backups and archive files, then shrink the file.

        Returns (removed results, removed archive files). Local audio/image folders are not touched.
        """
        if not self.path.is_file():
            return 0, 0
        db = self.connect()
        try:
            archived = {name for (name,) in db.execute(
                "SELECT DISTINCT m.filename FROM result_media m JOIN results r USING(key) "
                "WHERE r.source=? AND m.kind='archive'", (source,))}
            with db:
                count = db.execute('DELETE FROM results WHERE source=?', (source,)).rowcount
                db.execute('DELETE FROM assets WHERE NOT EXISTS '
                           '(SELECT 1 FROM result_media WHERE result_media.digest=assets.digest)')
                still_used = {name for (name,) in db.execute(
                    "SELECT DISTINCT filename FROM result_media WHERE kind='archive'")}
            db.execute('VACUUM')  # SQLite keeps freed pages until the file is rebuilt.
        finally:
            db.close()
        removed = 0
        folder = self.path.parent / 'media'
        for name in archived - still_used:
            path = folder / name
            if Path(name).name == name and path.is_file():
                path.unlink()
                removed += 1
        return count, removed

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
