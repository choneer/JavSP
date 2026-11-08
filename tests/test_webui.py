from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

from javsp import server


@pytest.fixture
def client(tmp_path, monkeypatch):
    config = tmp_path / 'config.yml'
    config.write_text((server.ROOT / 'config.yml').read_text(encoding='utf-8'), encoding='utf-8')
    monkeypatch.setattr(server, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(server, 'CONFIG', config)
    monkeypatch.setattr(server, 'process', None)
    monkeypatch.setattr(server, 'exit_code', None)
    server.lines.clear()
    with TestClient(server.app, base_url='http://127.0.0.1:8765') as instance:
        yield instance


def test_host_token_and_config_validation(client, tmp_path):
    assert client.get('/').status_code == 200
    assert client.get('/', headers={'host': 'attacker.example'}).status_code == 403
    state = client.get('/api/config').json()
    text, revision = state['text'], state['revision']
    assert client.put('/api/config', json={'text': text}).status_code == 403
    headers = {'x-javsp-token': server.TOKEN}
    assert client.put('/api/config', headers=headers, json={'text': 'not: valid', 'revision': revision}).status_code == 400
    assert (tmp_path / 'config.yml').read_text(encoding='utf-8') == text
    assert client.put('/api/config', headers=headers, json={'text': text, 'revision': revision}).status_code == 200


def test_empty_directory_job(client, tmp_path):
    headers = {'x-javsp-token': server.TOKEN}
    data = {'directory': str(tmp_path), 'confirm': False}
    assert client.post('/api/start', headers=headers, json=data).status_code == 400
    data['confirm'] = True
    assert client.post('/api/start', headers=headers, json=data).status_code == 200
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = client.get('/api/status').json()
        if not state['running'] and state['exit_code'] is not None:
            break
        time.sleep(.1)
    assert state['exit_code'] == 1, state
    assert not list(tmp_path.glob('.task-*.yml'))
    assert not list(tmp_path.glob('*.nfo'))


def test_rejects_bad_regex_and_unknown_template(client):
    state = client.get('/api/config').json()
    text, revision = state['text'], state['revision']
    headers = {'x-javsp-token': server.TOKEN}
    bad_regex = text.replace("- '(144|240|360|480|720|1080)[Pp]'", "- '['")
    assert bad_regex != text
    assert client.put('/api/config', headers=headers, json={'text': bad_regex, 'revision': revision}).status_code == 400
    bad_field = text.replace("basename_pattern: '{num}'", "basename_pattern: '{not_a_field}'", 1)
    assert bad_field != text
    assert client.put('/api/config', headers=headers, json={'text': bad_field, 'revision': revision}).status_code == 400


def test_stale_configuration_cannot_overwrite_newer_changes(client, tmp_path):
    state = client.get('/api/config').json()
    path = tmp_path / 'config.yml'
    changed = state['text'] + '\n# edited by another application\n'
    path.write_text(changed, encoding='utf-8')
    headers = {'x-javsp-token': server.TOKEN}
    response = client.put('/api/config', headers=headers,
                          json={'text': state['text'], 'revision': state['revision']})
    assert response.status_code == 409
    assert path.read_text(encoding='utf-8') == changed
    fresh = client.get('/api/config').json()
    assert fresh['revision'] != state['revision']
    assert client.put('/api/config', headers=headers,
                      json={'text': state['text'], 'revision': fresh['revision']}).status_code == 200


def test_quick_preview_preserves_other_values_and_does_not_save(client, tmp_path):
    import yaml
    result=client.get('/api/config').json()
    before=yaml.safe_load(result['text'])
    payload={'text':result['text'],'directory':str(tmp_path),'proxy':'http://127.0.0.1:6123',
             'minimum_size':'42MiB','move_files':False,'skip_nfo_dir':True,
             'normal_sources':['javdb','avsox'],'fc2_sources':['fc2']}
    headers={'x-javsp-token':server.TOKEN}
    assert client.post('/api/config/quick-preview',json=payload).status_code==403
    response=client.post('/api/config/quick-preview',headers=headers,json=payload)
    assert response.status_code==200, response.text
    after=yaml.safe_load(response.json()['text'])
    assert after['network']['proxy_server']=='http://127.0.0.1:6123'
    assert after['scanner']['input_directory']==str(tmp_path)
    assert after['crawler']['selection']['normal']==['javdb','avsox']
    assert after['crawler']['selection']['cid']==before['crawler']['selection']['cid']
    assert after['summarizer']['move_files'] is False
    assert (tmp_path/'config.yml').read_text(encoding='utf8')==result['text']
    payload['normal_sources']=['not-a-real-source']
    assert client.post('/api/config/quick-preview',headers=headers,json=payload).status_code==400


def test_invalid_disk_configuration_can_be_repaired(client, tmp_path):
    path = tmp_path / 'config.yml'
    valid = path.read_text(encoding='utf-8')
    path.write_text('scanner: [invalid\n', encoding='utf-8')
    state = client.get('/api/config').json()
    assert state['text'] == 'scanner: [invalid\n'
    assert state['quick'] is None and state['error']
    headers = {'x-javsp-token': server.TOKEN}
    response = client.put('/api/config', headers=headers,
                          json={'text': valid, 'revision': state['revision']})
    assert response.status_code == 200
    assert client.get('/api/config').json()['quick'] is not None
