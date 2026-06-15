#!/usr/bin/env python3
"""
index_sync.py — Full-backfill and verification CLI for the WAI fleet index.

Usage:
  python3 tools/index_sync.py --full              # Seed lugs + tracks + sessions from disk
  python3 tools/index_sync.py --lugs-only         # Seed only lugs
  python3 tools/index_sync.py --tracks-only       # Seed only session tracks
  python3 tools/index_sync.py --sessions-only     # Seed only session metadata
  python3 tools/index_sync.py --verify            # Compare row counts to disk file counts
  python3 tools/index_sync.py --drop-rebuild      # Drop all tables and rebuild from disk
  python3 tools/index_sync.py --full --supabase   # Seed all + push to Supabase remote

The local SQLite cache at WAI-Spoke/historian/cache.db is the target.
When --supabase is set with SUPABASE_KEY + SUPABASE_REST, also pushes to remote.
Disk is always authoritative — this script is safe to re-run at any time.
"""
import argparse
import glob
import json
import os
import sqlite3
import sys
import urllib.request
import urllib.error
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'WAI-Spoke'))

from db.local_cache import LocalCache

WHEEL_ID = 'a055479fb9bf'
CACHE_PATH = PROJECT_ROOT / 'WAI-Spoke/historian/cache.db'


def _supabase_upsert_batch(rows, table, rest_url, key):
    """
    POST rows to Supabase table with upsert semantics.
    Returns (ok_count, error_count).
    """
    if not rows:
        return 0, 0

    ok = errors = 0
    batch_size = 200

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        payload = json.dumps(batch, ensure_ascii=False).encode('utf-8')
        url = f'{rest_url}/{table}'

        req = urllib.request.Request(
            url,
            data=payload,
            method='POST',
            headers={
                'Content-Type': 'application/json',
                'apikey': key,
                'Authorization': f'Bearer {key}',
                'Prefer': 'resolution=merge-duplicates'
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status in (200, 201):
                    ok += len(batch)
                else:
                    errors += len(batch)
        except (urllib.error.HTTPError, urllib.error.URLError, Exception) as e:
            errors += len(batch)
            print(f'  Supabase batch error {table}: {e}', file=sys.stderr)

    return ok, errors


def _scalar(v):
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return json.dumps(v, ensure_ascii=False)


def seed_lugs(cache: LocalCache, verbose=False, supabase_enabled=False) -> tuple[int, int]:
    pattern = str(PROJECT_ROOT / 'WAI-Spoke/lugs/bytype/**/*.json')
    files = glob.glob(pattern, recursive=True)
    ok = errors = 0
    supabase_rows = []

    for f in files:
        try:
            d = json.load(open(f))
            row = {
                'id':         _scalar(d.get('id') or d.get('i') or ''),
                'wheel_id':   WHEEL_ID,
                'ty':         _scalar(d.get('ty') or d.get('type', '')),
                'status':     _scalar(d.get('s') or d.get('status', '')),
                'title':      _scalar(d.get('t') or d.get('title', '')),
                'routed_to':  _scalar(d.get('rt') or d.get('routed_to', '')),
                'outcome':    _scalar(d.get('outcome')),
                'created_at': _scalar(d.get('ca') or d.get('created_at', '')),
                'updated_at': _scalar(d.get('updated_at') or d.get('ca') or d.get('created_at', '')),
            }
            cache.upsert_lug(row)
            if supabase_enabled:
                supabase_rows.append(row)
            ok += 1
        except Exception as e:
            if verbose:
                print(f'  lug error {f}: {e}', file=sys.stderr)
            errors += 1

    if supabase_enabled and supabase_rows:
        supabase_key = os.environ.get('SUPABASE_KEY', '')
        supabase_rest = os.environ.get('SUPABASE_REST', '')
        if supabase_key and supabase_rest:
            s_ok, s_err = _supabase_upsert_batch(supabase_rows, 'lugs', supabase_rest, supabase_key)
            errors += s_err
        elif verbose:
            print('  Warning: SUPABASE_KEY or SUPABASE_REST not set, skipping Supabase sync', file=sys.stderr)

    return ok, errors


_TRACKS_COLUMNS = ('id', 'wheel_id', 'session_id', 'turn_index', 'ts',
                   'event_type', 'content_summary', 'lug_ids', 'model_id')


def seed_tracks(cache: LocalCache, verbose=False, supabase_enabled=False) -> tuple[int, int]:
    sessions_dir = PROJECT_ROOT / 'WAI-Spoke/sessions'
    if not sessions_dir.exists():
        return 0, 0
    ok = errors = 0
    supabase_rows = []

    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        track_file = session_dir / 'track.jsonl'
        if not track_file.exists():
            continue
        session_id = session_dir.name
        turn_index = 0
        for line in open(track_file):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                turn_index += 1
                synthetic_id = f'{WHEEL_ID}:{session_id}:{turn_index}'
                row = {
                    'id':              synthetic_id,
                    'wheel_id':        WHEEL_ID,
                    'session_id':      session_id,
                    'turn_index':      entry.get('turn', turn_index),
                    'ts':              _scalar(entry.get('ts') or entry.get('timestamp')),
                    'event_type':      _scalar(entry.get('event') or entry.get('action')),
                    'content_summary': _scalar(entry.get('thinking') or entry.get('focus')),
                    'lug_ids':         _scalar(entry.get('activity')),
                    'model_id':        None,
                    'tokens_used':     None,
                    'created_at':      _scalar(entry.get('ts') or entry.get('timestamp')),
                }
                cache.upsert_track(row)
                if supabase_enabled:
                    supabase_rows.append(row)
                ok += 1
            except Exception as e:
                if verbose:
                    print(f'  track error {track_file}:{turn_index}: {e}', file=sys.stderr)
                errors += 1

    if supabase_enabled and supabase_rows:
        supabase_key = os.environ.get('SUPABASE_KEY', '')
        supabase_rest = os.environ.get('SUPABASE_REST', '')
        if supabase_key and supabase_rest:
            # Normalize all rows to the canonical column set before batching.
            # PostgREST PGRST102 fires when rows in a batch have different key sets.
            normalized = [{col: r.get(col) for col in _TRACKS_COLUMNS} for r in supabase_rows]
            s_ok, s_err = _supabase_upsert_batch(normalized, 'tracks', supabase_rest, supabase_key)
            errors += s_err
        elif verbose:
            print('  Warning: SUPABASE_KEY or SUPABASE_REST not set, skipping Supabase sync', file=sys.stderr)

    return ok, errors


def seed_sessions(cache: LocalCache, verbose=False, supabase_enabled=False) -> tuple[int, int]:
    sessions_dir = PROJECT_ROOT / 'WAI-Spoke/sessions'
    if not sessions_dir.exists():
        return 0, 0
    ok = errors = 0
    supabase_rows = []

    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        session_id = session_dir.name
        track_file = session_dir / 'track.jsonl'
        started_at = ended_at = session_kind = None
        completed_lugs = []
        if track_file.exists():
            for line in open(track_file):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    ev = entry.get('event', '')
                    ts = entry.get('ts') or entry.get('timestamp')
                    if ev == 'session_start' and not started_at:
                        started_at = ts
                    if ev in ('closeout', 'savepoint', 'lug_completed'):
                        ended_at = ts
                    if ev == 'lug_completed':
                        lid = entry.get('lug_id')
                        if lid:
                            completed_lugs.append(lid)
                    if entry.get('mode') == 'autonomous':
                        session_kind = 'autonomous'
                except Exception:
                    pass
        try:
            row = {
                'id':            session_id,
                'wheel_id':      WHEEL_ID,
                'started_at':    started_at,
                'ended_at':      ended_at,
                'model_id':      None,
                'session_kind':  session_kind or 'user',
                'outcome':       None,
                'turn_count':    None,
                'tokens_used':   None,
                'created_at':    started_at,
            }
            cache.upsert_session(row)
            if supabase_enabled:
                supabase_rows.append(row)
            ok += 1
        except Exception as e:
            if verbose:
                print(f'  session error {session_id}: {e}', file=sys.stderr)
            errors += 1

    if supabase_enabled and supabase_rows:
        supabase_key = os.environ.get('SUPABASE_KEY', '')
        supabase_rest = os.environ.get('SUPABASE_REST', '')
        if supabase_key and supabase_rest:
            s_ok, s_err = _supabase_upsert_batch(supabase_rows, 'sessions', supabase_rest, supabase_key)
            errors += s_err
        elif verbose:
            print('  Warning: SUPABASE_KEY or SUPABASE_REST not set, skipping Supabase sync', file=sys.stderr)

    return ok, errors


def _supabase_get_count(table, rest_url, key):
    """GET row count from Supabase table using Content-Range header."""
    try:
        url = f'{rest_url}/{table}?select=count'
        req = urllib.request.Request(
            url,
            method='GET',
            headers={
                'apikey': key,
                'Authorization': f'Bearer {key}',
                'Prefer': 'count=exact'
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_range = resp.headers.get('Content-Range', '')
            if content_range:
                parts = content_range.split('/')
                if len(parts) >= 2:
                    return int(parts[1])
        return None
    except Exception as e:
        print(f'  Error fetching Supabase count for {table}: {e}', file=sys.stderr)
        return None


def verify(cache: LocalCache, supabase_enabled=False):
    import json as _json
    # Disk counts — use unique IDs (dedup is correct; primary key is id)
    lug_ids = set()
    for f in glob.glob(str(PROJECT_ROOT / 'WAI-Spoke/lugs/bytype/**/*.json'), recursive=True):
        try:
            d = _json.load(open(f))
            lid = d.get('id', d.get('i'))
            if lid:
                lug_ids.add(lid)
        except Exception:
            pass
    lug_files = len(lug_ids)
    session_dirs = len([d for d in (PROJECT_ROOT / 'WAI-Spoke/sessions').iterdir() if d.is_dir()]) if (PROJECT_ROOT / 'WAI-Spoke/sessions').exists() else 0
    # Track lines: count only parseable JSONL lines
    track_lines = 0
    if (PROJECT_ROOT / 'WAI-Spoke/sessions').exists():
        for sd in (PROJECT_ROOT / 'WAI-Spoke/sessions').iterdir():
            tf = sd / 'track.jsonl'
            if tf.exists():
                for line in open(tf):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        _json.loads(line)
                        track_lines += 1
                    except Exception:
                        pass

    # Cache counts
    conn = sqlite3.connect(str(CACHE_PATH))
    lug_rows    = conn.execute('SELECT COUNT(*) FROM lugs').fetchone()[0]
    track_rows  = conn.execute('SELECT COUNT(*) FROM tracks').fetchone()[0]
    session_rows = conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
    conn.close()

    # Supabase counts (if enabled)
    supabase_lug_rows = supabase_track_rows = supabase_session_rows = None
    if supabase_enabled:
        supabase_key = os.environ.get('SUPABASE_KEY', '')
        supabase_rest = os.environ.get('SUPABASE_REST', '')
        if supabase_key and supabase_rest:
            supabase_lug_rows = _supabase_get_count('lugs', supabase_rest, supabase_key)
            supabase_track_rows = _supabase_get_count('tracks', supabase_rest, supabase_key)
            supabase_session_rows = _supabase_get_count('sessions', supabase_rest, supabase_key)

    if supabase_enabled and (supabase_lug_rows is not None or supabase_track_rows is not None or supabase_session_rows is not None):
        print(f'{"Source":<20} {"Disk":>8} {"Cache":>8} {"Supabase":>9} {"Match":>6}')
        print('-' * 63)
        print(f'{"lugs":<20} {lug_files:>8} {lug_rows:>8} {supabase_lug_rows if supabase_lug_rows is not None else "N/A":>9} {"OK" if supabase_lug_rows is not None and supabase_lug_rows >= lug_rows >= lug_files else "DELTA":>6}')
        print(f'{"track entries":<20} {track_lines:>8} {track_rows:>8} {supabase_track_rows if supabase_track_rows is not None else "N/A":>9} {"OK" if supabase_track_rows is not None and supabase_track_rows >= track_rows >= track_lines else "DELTA":>6}')
        print(f'{"sessions":<20} {session_dirs:>8} {session_rows:>8} {supabase_session_rows if supabase_session_rows is not None else "N/A":>9} {"OK" if supabase_session_rows is not None and supabase_session_rows >= session_rows >= session_dirs else "DELTA":>6}')
    else:
        print(f'{"Source":<20} {"Disk":>8} {"Cache":>8} {"Match":>6}')
        print('-' * 46)
        print(f'{"lugs":<20} {lug_files:>8} {lug_rows:>8} {"OK" if lug_rows >= lug_files else "DELTA":>6}')
        print(f'{"track entries":<20} {track_lines:>8} {track_rows:>8} {"OK" if track_rows >= track_lines else "DELTA":>6}')
        print(f'{"sessions":<20} {session_dirs:>8} {session_rows:>8} {"OK" if session_rows >= session_dirs else "DELTA":>6}')

    return lug_rows >= lug_files and session_rows >= session_dirs


def drop_rebuild(cache: LocalCache):
    conn = sqlite3.connect(str(CACHE_PATH))
    conn.execute('DELETE FROM lugs')
    conn.execute('DELETE FROM tracks')
    conn.execute('DELETE FROM sessions')
    conn.commit()
    conn.close()
    print('All rows cleared. Rebuilding from disk...')
    seed_all(cache, verbose=True)


def seed_all(cache: LocalCache, verbose=False, supabase_enabled=False):
    cache.initialize_db()
    lug_ok, lug_err = seed_lugs(cache, verbose, supabase_enabled)
    print(f'Lugs:     {lug_ok:>5} seeded  {lug_err:>3} errors')
    trk_ok, trk_err = seed_tracks(cache, verbose, supabase_enabled)
    print(f'Tracks:   {trk_ok:>5} seeded  {trk_err:>3} errors')
    ses_ok, ses_err = seed_sessions(cache, verbose, supabase_enabled)
    print(f'Sessions: {ses_ok:>5} seeded  {ses_err:>3} errors')

    if supabase_enabled:
        total_err = lug_err + trk_err + ses_err
        print(f'Supabase: {lug_ok} lugs, {trk_ok} tracks, {ses_ok} sessions upserted ({total_err} errors)')
        retry_queue_path = PROJECT_ROOT / 'tools/sync_retry_queue.jsonl'
        if retry_queue_path.exists():
            try:
                retry_queue_path.write_text('')
                print('Cleared sync_retry_queue.jsonl')
            except Exception as e:
                print(f'Warning: Could not clear sync_retry_queue.jsonl: {e}', file=sys.stderr)

    cache.close()


def main():
    parser = argparse.ArgumentParser(description='WAI fleet index sync CLI')
    parser.add_argument('--full',          action='store_true', help='Seed lugs + tracks + sessions')
    parser.add_argument('--lugs-only',     action='store_true', help='Seed only lugs')
    parser.add_argument('--tracks-only',   action='store_true', help='Seed only session tracks')
    parser.add_argument('--sessions-only', action='store_true', help='Seed only session metadata')
    parser.add_argument('--verify',        action='store_true', help='Compare disk vs cache row counts')
    parser.add_argument('--drop-rebuild',  action='store_true', help='Drop all rows, rebuild from disk')
    parser.add_argument('--supabase',      action='store_true', help='Also push to Supabase (requires SUPABASE_KEY + SUPABASE_REST env vars)')
    parser.add_argument('--verbose',       action='store_true', help='Print per-file errors')
    args = parser.parse_args()

    cache = LocalCache(CACHE_PATH)
    cache.initialize_db()

    if args.drop_rebuild:
        drop_rebuild(cache)
    elif args.full:
        seed_all(cache, args.verbose, args.supabase)
    elif args.lugs_only:
        ok, err = seed_lugs(cache, args.verbose, args.supabase)
        cache.close()
        print(f'Lugs: {ok} seeded, {err} errors')
    elif args.tracks_only:
        ok, err = seed_tracks(cache, args.verbose, args.supabase)
        cache.close()
        print(f'Tracks: {ok} seeded, {err} errors')
    elif args.sessions_only:
        ok, err = seed_sessions(cache, args.verbose, args.supabase)
        cache.close()
        print(f'Sessions: {ok} seeded, {err} errors')
    elif args.verify:
        cache.close()
        ok = verify(cache, args.supabase)
        sys.exit(0 if ok else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
