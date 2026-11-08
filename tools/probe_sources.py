"""Isolated, non-writing online probes using public upstream test IDs."""
import concurrent.futures
import importlib
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SITES = ['airav','avsox','javbus','javdb','javlib','jav321','mgstage','prestige','fc2','javmenu','fc2ppvdb','fanza','dl_getchu','gyutto']


def sample(site):
    for path in sorted((ROOT / 'unittest' / 'data').glob('*.json')):
        match = re.fullmatch(r'([-\w]+)\s+\((\w+)\)\.json', path.name)
        if match and match.group(2) == site:
            data = json.loads(path.read_text(encoding='utf-8'))
            if data.get('title') and data.get('cover'):
                return match.group(1)
    return 'FC2-4497837' if site == 'fc2ppvdb' else None


def worker(site, avid):
    # Avoid accessing a user's browser credentials even on redirects.
    logging.disable(logging.CRITICAL)
    from javsp.datatype import MovieInfo
    from javsp.web.exceptions import SiteBlocked, CredentialError, MovieNotFoundError
    try:
        mod = importlib.import_module('javsp.web.' + site)
        if site == 'javdb':
            mod.cookies_pool = []
            mod.get_browsers_cookies = lambda: []
        movie = MovieInfo(cid=avid) if site == 'fanza' else MovieInfo(avid)
        getattr(mod, 'parse_clean_data', mod.parse_data)(movie)
        result = 'ok' if movie.title and movie.cover else 'missing_required_fields'
        return {'site': site, 'sample': avid, 'status': result, 'title': bool(movie.title), 'cover': bool(movie.cover)}
    except (SiteBlocked, CredentialError, MovieNotFoundError) as e:
        return {'site': site, 'sample': avid, 'status': type(e).__name__}
    except Exception as e:
        return {'site': site, 'sample': avid, 'status': 'error', 'type': type(e).__name__, 'detail': str(e)[:300]}


def run(site):
    avid = sample(site)
    if not avid:
        return {'site': site, 'status': 'no_positive_sample'}
    env = {k:v for k,v in os.environ.items() if not k.upper().startswith('JAVSP_') and k.upper() not in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY')}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    try:
        command = [sys.executable, '-m', 'tools.probe_sources', '--worker', site, avid]
        if os.environ.get('JAVSP_PROBE_CONFIG'):
            command.extend(['-c', os.environ['JAVSP_PROBE_CONFIG']])
        p = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=50)
        return json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else {'site':site, 'status':'worker_error','detail':p.stderr[-400:]}
    except subprocess.TimeoutExpired:
        return {'site':site,'status':'timeout'}
    except Exception as e:
        return {'site':site,'status':'probe_error','type':type(e).__name__}


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        print(json.dumps(worker(sys.argv[2], sys.argv[3]), ensure_ascii=False))
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for result in pool.map(run, SITES):
                print(json.dumps(result, ensure_ascii=False), flush=True)
