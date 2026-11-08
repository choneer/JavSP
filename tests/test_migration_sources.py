from pathlib import Path
from types import SimpleNamespace

import pytest
from lxml import html

from javsp.datatype import MovieInfo
from javsp.web import fc2, javmenu
from tools.migrate_windows import migrate

ROOT = Path(__file__).resolve().parents[1]


def test_migration_handles_missing_legacy_fields(tmp_path):
    ini = tmp_path / 'old.ini'
    ini.write_text('''[File]\nscan_dir=\nmedia_ext=mp4;mkv\nignore_folder=#skip\nignore_video_file_less_than=1\nenable_file_move=no\n[Network]\nuse_proxy=no\n[NamingRule]\noutput_folder=#output\nsave_dir=$actress/$title\nfilename=$num\nmax_path_len=250\nmax_actress_count=10\n[Picture]\nuse_ai_crop=no\n[Translate]\nengine=\n''', encoding='utf-8')
    result, warnings = migrate(ini, ROOT / 'config.yml')
    assert result['scanner']['manual'] is False
    assert result['scanner']['filename_extensions'] == ['.mp4', '.mkv']
    assert result['summarizer']['path']['output_folder_pattern'] == '#output/{actress}/{title}'
    assert result['summarizer']['extra_fanarts']['scrap_interval'] == 'PT1.5S'
    assert result['other']['auto_update'] is False
    assert warnings == []


def test_fc2_updated_release_date_and_missing_optional_date(monkeypatch):
    markup = '''<html><div class="items_article_left"><div class="items_article_headerInfo"><h3>Example</h3></div>
    <div class="items_article_MainitemThumb"><span><img src="https://example.test/img"><p class="items_article_info">00:30:00</p></span></div>
    <li>by <a>Creator</a></li>{date}<a class="items_article_Stars"><p><span class="items_article_Star5"></span></p></a></div></html>'''
    monkeypatch.setattr(fc2, 'Cfg', lambda: SimpleNamespace(crawler=SimpleNamespace(hardworking=False)))
    for date, expected in [('<div class="items_article_softDevice"><p>販売日 : 2024/11/09</p></div>', '2024-11-09'), ('', None)]:
        monkeypatch.setattr(fc2, 'request_get', lambda url: SimpleNamespace(url=url))
        monkeypatch.setattr(fc2, 'resp2html', lambda response: html.fromstring(markup.format(date=date)))
        movie = MovieInfo('FC2-123')
        fc2.parse_data(movie)
        assert movie.publish_date == expected
        assert movie.title == 'Example'
        assert movie.cover == 'https://example.test/img'


def test_javmenu_new_layout_and_optional_fields(monkeypatch):
    doc = '''<html><head><meta property="og:image" content="/cover.jpg"></head><body>
    <h1><strong>FC2-123 Example 免費AV在線看</strong></h1><div class="card-body">
    <div><span>發佈於:</span><span>2024-01-01</span></div><div><span>時長:</span><span>42分鐘</span></div>
    <a class="genre" href="/fc2/genre/42">genre</a></div><a data-fancybox="gallery" href="/sample.jpg"></a></body></html>'''
    monkeypatch.setattr(javmenu.request, 'get', lambda url: SimpleNamespace(history=[], url=url))
    monkeypatch.setattr(javmenu, 'resp2html', lambda r: html.fromstring(doc))
    movie = MovieInfo('FC2-123')
    javmenu.parse_data(movie)
    assert movie.title == 'Example'
    assert movie.cover == 'https://mrzyx.xyz/cover.jpg'
    assert movie.publish_date == '2024-01-01'
    assert movie.duration == '42'
    assert movie.preview_pics == ['https://mrzyx.xyz/sample.jpg']


def test_scan_ignored_folder_with_nfo_and_empty_patterns(tmp_path, monkeypatch):
    from javsp import file as file_module
    ignored = tmp_path / '#skip'
    ignored.mkdir()
    (ignored / 'movie.nfo').write_text('', encoding='utf-8')
    scanner = SimpleNamespace(ignored_folder_name_pattern=['^#skip$'], skip_nfo_dir=True,
                              filename_extensions=['.mp4'], minimum_size=1)
    monkeypatch.setattr(file_module, 'Cfg', lambda: SimpleNamespace(scanner=scanner))
    assert file_module.scan_movies(str(tmp_path)) == []
    scanner.ignored_folder_name_pattern = []
    assert file_module.scan_movies(str(tmp_path)) == []


def test_javdb_actor_layout_and_legacy_markers(monkeypatch):
    from javsp.web import javdb
    search = html.fromstring('''<html><div class="video-title"><strong>IPX-177</strong></div>
    <a class="box" href="https://javdb.com/v/sample"></a></html>''')
    detail = html.fromstring('''<html><body><section><div><div class="video-detail">
    <h2><strong class="current-title">IPX-177 Sample</strong></h2><img class="video-cover" src="https://example.test/image.jpg">
    <nav class="panel movie-panel-info"><div><span>IPX-177</span></div>
    <div><strong>日期:</strong><span>2020-01-01</span></div>
    <div><strong>時長:</strong><span>120分鍾</span></div>
    <div><strong>演員:</strong><span><a class="actor-female">Female A</a>, <a>Male</a>, <a>Female B</a><strong>♀</strong></span></div>
    </nav></div></div></section></body></html>''')
    monkeypatch.setattr(javdb, 'get_html_wrapper', lambda url: search if '/search?' in url else detail)
    movie = MovieInfo('IPX-177')
    javdb.parse_data(movie)
    assert movie.actress == ['Female A', 'Female B']
    assert movie.title == 'Sample'


def test_javdb_summary_cover_fallback_in_subprocess():
    import subprocess
    import sys
    program = '''from javsp.__main__ import info_summary\nfrom javsp.datatype import Movie,MovieInfo\nm=Movie("IPX-177");m.files=["IPX-177.mp4"]\ni=MovieInfo("IPX-177");i.title="Example";i.cover="https://example.test/cover.jpg"\nassert info_summary(m,{"javdb":i});assert m.info.cover==i.cover\n'''
    result = subprocess.run([sys.executable, '-c', program], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_fanza_search_selects_requested_cid(monkeypatch):
    from javsp.web import fanza
    doc = html.fromstring('''<html><ul id="list">
    <li><div><p><a href="https://www.dmm.co.jp/digital/videoa/-/detail/=/cid=wanted123/">wanted</a></p></div></li>
    <li><div><p><a href="https://www.dmm.co.jp/digital/videoa/-/detail/=/cid=other456/">other</a></p></div></li>
    </ul></html>''')
    monkeypatch.setattr(fanza.request, 'get', lambda url: SimpleNamespace(status_code=200, raise_for_status=lambda: None))
    monkeypatch.setattr(fanza, 'resp2html_wrapper', lambda response: doc)
    result = fanza.get_urls_of_cid('wanted123')
    assert len(result) == 1 and 'cid=wanted123' in result[0]['url']


def test_javbus_reports_age_verification(monkeypatch):
    from javsp.web import javbus
    from javsp.web.exceptions import CredentialError
    monkeypatch.setattr(javbus, 'request_get', lambda *a, **kw: SimpleNamespace(url='https://www.javbus.com/doc/driver-verify'))
    with pytest.raises(CredentialError):
        javbus.parse_data(MovieInfo('IPX-177'))


def test_download_failure_preserves_existing_file(tmp_path, monkeypatch):
    import requests
    from javsp.web import base
    target = tmp_path / 'cover.jpg'
    target.write_bytes(b'original')
    class BadResponse:
        headers = {}
        def raise_for_status(self): raise requests.HTTPError('HTTP 403')
        def close(self): pass
    monkeypatch.setattr(base.requests, 'get', lambda *args, **kwargs: BadResponse())
    with pytest.raises(requests.HTTPError):
        base.download('https://example.test/cover.jpg', str(target))
    assert target.read_bytes() == b'original'
    assert sorted(x.name for x in tmp_path.iterdir()) == ['cover.jpg']


def test_non_image_response_does_not_replace_cover(tmp_path, monkeypatch):
    from javsp.web import base
    target = tmp_path / 'cover.jpg'
    target.write_bytes(b'original')
    class Response:
        headers = {'Content-Length': '4'}
        def raise_for_status(self): pass
        def iter_content(self, chunk_size): yield b'html'
        def close(self): pass
    monkeypatch.setattr(base.requests, 'get', lambda *args, **kwargs: Response())
    with pytest.raises(OSError):
        base.download('https://example.test/cover.jpg', str(target))
    assert target.read_bytes() == b'original'
    assert sorted(x.name for x in tmp_path.iterdir()) == ['cover.jpg']


def test_fanza_modern_graphql_maps_fields(monkeypatch):
    from javsp.web import fanza
    content = {'id':'sample123','title':'Example','description':'Plot','makerContentId':'ABC-123',
               'duration':3600,'deliveryStartDate':'2024-03-01T00:00:00Z',
               'packageImage':{'largeUrl':'https://example.test/cover.jpg'},
               'sampleImages':[{'largeImageUrl':'https://example.test/1.jpg'}],
               'maker':{'name':'Maker'},'actresses':[{'name':'Actor'}]}
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'data': {'ppvContent': content}}
    monkeypatch.setattr(fanza.requests, 'post', lambda *args, **kwargs: Response())
    movie=MovieInfo(cid='sample123')
    fanza.parse_modern_content(movie)
    assert movie.cid == 'sample123' and movie.dvdid == 'ABC-123'
    assert movie.title == 'Example' and movie.duration == '60'
    assert movie.publish_date == '2024-03-01' and movie.actress == ['Actor']
    assert movie.cover.endswith('/cover.jpg') and len(movie.preview_pics) == 1


def test_batch_continues_after_individual_failure(tmp_path):
    import subprocess
    import sys
    program = r'''from types import SimpleNamespace as S
from pathlib import Path
import sys
from javsp import __main__ as app
from javsp.datatype import Movie
out=Path(sys.argv[1]); first=Movie("ABC-111"); first.files=[str(out/"ABC-111.mp4")]; second=Movie("ABC-222");second.files=[str(out/"ABC-222.mp4")]
app.Cfg=lambda:S(translator=S(engine=None),summarizer=S(extra_fanarts=S(enabled=False),cover=S(highres=False),move_files=False),crawler=S(selection={"normal":["site"]},sleep_after_scraping=0))
app.parallel_crawler=lambda movie,bar: {} if movie is first else {"site":object()}
def summary(movie,info): movie.info=S(covers=["url"],big_covers=[],cover="url"); return True
def names(movie): movie.save_dir=str(out);movie.fanart_file=str(out/"fanart.jpg");movie.poster_file=str(out/"poster.jpg");movie.nfo_file=str(out/"movie.nfo")
app.info_summary=summary;app.generate_names=names;app.download_cover=lambda covers,path:("url",path);app.process_poster=lambda movie:None;app.write_nfo=lambda info,path:None
result=app.RunNormalMode([first,second]);assert result==[second]
'''
    result = subprocess.run([sys.executable, '-c', program, str(tmp_path)], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert result.returncode == 0, result.stderr


def test_move_preflight_detects_conflict_before_any_move(tmp_path):
    from javsp.datatype import Movie
    source = tmp_path / 'source'
    dest = tmp_path / 'dest'
    source.mkdir(); dest.mkdir()
    one = source / 'ABC-123-CD1.mp4'; two = source / 'ABC-123-CD2.mp4'
    one.write_bytes(b'one'); two.write_bytes(b'two')
    existing = dest / 'ABC-123-CD2.mp4'; existing.write_bytes(b'existing')
    movie = Movie('ABC-123'); movie.files = [str(one), str(two)]
    movie.save_dir = str(dest); movie.basename = 'ABC-123'
    with pytest.raises(FileExistsError):
        movie.rename_files()
    assert one.read_bytes() == b'one' and two.read_bytes() == b'two'
    assert existing.read_bytes() == b'existing'
    assert not (dest / 'ABC-123-CD1.mp4').exists()


def test_javlibrary_rejects_challenge_and_unrelated_page(monkeypatch):
    from javsp.web import javlib
    from javsp.web.exceptions import SiteBlocked, WebsiteError
    monkeypatch.setattr(javlib, 'base_url', 'https://www.javlibrary.com')
    monkeypatch.setattr(javlib.request, 'get', lambda *args, **kwargs: SimpleNamespace(status_code=403))
    with pytest.raises(SiteBlocked):
        javlib.parse_data(MovieInfo('IPX-177'))
    response = SimpleNamespace(status_code=200, history=[], url='https://www.javlibrary.com/search', raise_for_status=lambda:None)
    monkeypatch.setattr(javlib.request, 'get', lambda *args, **kwargs: response)
    monkeypatch.setattr(javlib, 'resp2html', lambda r: html.fromstring('<html><body>wrong site</body></html>'))
    with pytest.raises(WebsiteError):
        javlib.parse_data(MovieInfo('IPX-177'))


def test_avsox_spa_search_and_detail(monkeypatch):
    from javsp.web import avsox
    page = html.fromstring('<html><div id="javu-site-index"></div></html>')
    monkeypatch.setattr(avsox, 'get_html', lambda url: page)
    monkeypatch.setattr(avsox, 'base_url', 'https://example.test/')
    class Response:
        def __init__(self, data=None):
            self.content=b'<html><meta name="csrf-token" content="test-token"></html>'
            self.data=data
        def raise_for_status(self): pass
        def json(self): return {'code': 200, 'data':self.data}
    class Session:
        def __init__(self): self.proxies={}; self.headers={}
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def get(self,*args,**kwargs): return Response()
        def post(self,url,json,timeout):
            if url.endswith('/search'):
                return Response([{'movieId':'id1','movieFanHao':'ABC-123'}])
            return Response({'movieId':'id1','movieFanHao':'ABC-123','title':'Example',
                             'posterLarge':'/cover.jpg','length':60,'releaseDate':'2024-01-01',
                             'studio':{'studioName':'Studio'},'series':{'seriesName':'Series'},
                             'star':[{'starName':'Actor'}],'genre':[{'genreName':'Genre'}]})
    monkeypatch.setattr(avsox.requests, 'Session', Session)
    movie=MovieInfo('ABC-123');avsox.parse_data(movie)
    assert movie.title=='Example' and movie.cover=='https://example.test/cover.jpg'
    assert movie.actress==['Actor'] and movie.genre==['Genre'] and movie.duration=='60'
    assert movie.url=='https://example.test/tw/movies/id1'


def test_parallel_crawler_uses_cleaned_parser():
    import subprocess
    import sys
    program = '''from types import SimpleNamespace as S\nimport sys\nfrom javsp import __main__ as app\nfrom javsp.datatype import Movie\nclass Selection:\n def __getitem__(self,key): return [S(value="fake")]\nclass Config:\n crawler=S(selection=Selection())\n network=S(retry=1)\napp.Cfg=Config\ndef raw(info): info.title="raw"\ndef clean(info): info.title="clean"\nsys.modules["javsp.web.fake"]=S(parse_data=raw,parse_clean_data=clean)\nm=Movie("IPX-177");m.files=["IPX-177.mp4"];out=app.parallel_crawler(m);assert out["fake"].title=="clean"\n'''
    result = subprocess.run([sys.executable, '-c', program], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf8', errors='replace')
    assert result.returncode == 0, result.stderr


def test_parallel_crawler_reports_final_network_failure():
    import subprocess
    import sys
    program = '''from types import SimpleNamespace as S\nimport sys,logging,requests\nfrom javsp import __main__ as app\nfrom javsp.datatype import Movie\nlogging.basicConfig(level=logging.INFO)\nclass Selection:\n def __getitem__(self,key): return [S(value="fake")]\nclass Config:\n crawler=S(selection=Selection())\n network=S(retry=2)\napp.Cfg=Config\ndef fail(info): raise requests.Timeout("private request details")\nsys.modules["javsp.web.fake"]=S(parse_data=fail)\nm=Movie("IPX-177");m.files=["IPX-177.mp4"];assert app.parallel_crawler(m)=={}\n'''
    result = subprocess.run([sys.executable, '-c', program], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf8', errors='replace')
    assert result.returncode == 0, result.stderr
    assert 'network request failed after 2 attempt(s): Timeout' in result.stderr
    assert 'private request details' not in result.stderr


def test_javdb_browser_cookies_are_opt_in(monkeypatch):
    from javsp.web import javdb
    from javsp.web.exceptions import CredentialError
    response = SimpleNamespace(status_code=200, history=[object()], url='https://javdb.com/login')
    monkeypatch.setattr(javdb.request, 'get', lambda *a, **kw: response)
    monkeypatch.setattr(javdb, 'Cfg', lambda: SimpleNamespace(crawler=SimpleNamespace(javdb_browser_cookies=False)))
    def forbidden(): raise AssertionError('browser cookie access was not authorized')
    monkeypatch.setattr(javdb, 'get_browsers_cookies', forbidden)
    with pytest.raises(CredentialError, match='disabled'):
        javdb.get_html_wrapper('https://javdb.com/v/example')


def test_scan_reports_duplicates_and_unrecognized_items(tmp_path, monkeypatch):
    from javsp import file as file_module
    for dirname, filename in [('a','duplicate.mp4'),('b','duplicate.mp4'),('c','unknown.mp4'),('d','good.mp4')]:
        folder=tmp_path/dirname;folder.mkdir();(folder/filename).write_bytes(b'x')
    scanner=SimpleNamespace(ignored_folder_name_pattern=[],skip_nfo_dir=False,
                            filename_extensions=['.mp4'],minimum_size=1)
    monkeypatch.setattr(file_module,'Cfg',lambda:SimpleNamespace(scanner=scanner))
    monkeypatch.setattr(file_module,'get_id',lambda path: 'ABC-123' if 'duplicate' in Path(path).name else 'DEF-456' if 'good' in Path(path).name else None)
    monkeypatch.setattr(file_module,'get_cid',lambda path: None)
    monkeypatch.setattr(file_module,'guess_av_type',lambda avid: 'normal')
    result=file_module.scan_movies(str(tmp_path))
    assert len(result)==1 and result[0].dvdid=='DEF-456'
    assert len(file_module.get_failed_when_scan())==2
    empty=tmp_path/'empty';empty.mkdir()
    assert file_module.scan_movies(str(empty))==[]
    assert file_module.get_failed_when_scan()==[]


def test_scan_records_unreadable_subdirectory(tmp_path, monkeypatch):
    from javsp import file as file_module
    folder=tmp_path/'blocked';folder.mkdir()
    scanner=SimpleNamespace(ignored_folder_name_pattern=[],skip_nfo_dir=True,
                            filename_extensions=['.mp4'],minimum_size=1)
    monkeypatch.setattr(file_module,'Cfg',lambda:SimpleNamespace(scanner=scanner))
    real_listdir=file_module.os.listdir
    def listdir(path):
        if str(path)==str(folder): raise PermissionError('denied')
        return real_listdir(path)
    monkeypatch.setattr(file_module.os,'listdir',listdir)
    assert file_module.scan_movies(str(tmp_path))==[]
    assert len(file_module.get_failed_when_scan())==1


def test_entry_reports_partial_scan_as_failure(tmp_path):
    import subprocess
    import sys
    program = '''from types import SimpleNamespace as S\nimport sys\nfrom javsp import __main__ as app\nfrom javsp.datatype import Movie\nclass Config:\n crawler=S(normalize_actress_name=False)\n other=S(check_update=False,auto_update=False)\n scanner=S(input_directory=None,manual=False)\napp.Cfg=Config\napp.check_update=lambda *a:None\napp.get_scan_dir=lambda *a:sys.argv[1]\napp.import_crawlers=lambda:None\nm=Movie("ABC-123");m.files=[sys.argv[1]+"/ABC-123.mp4"]\napp.scan_movies=lambda root:[m]\napp.get_failed_when_scan=lambda:[object()]\napp.RunNormalMode=lambda movies:movies\napp.entry()\n'''
    result = subprocess.run([sys.executable, '-c', program, str(tmp_path)], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf8', errors='replace')
    assert result.returncode == 1, result.stderr
