"""从avsox抓取数据"""
import logging
from urllib.parse import quote, urljoin

import requests
from lxml import html as lxml_html

from javsp.web.base import get_html, read_proxy
from javsp.web.exceptions import *
from javsp.config import Cfg, CrawlerID
from javsp.datatype import MovieInfo


logger = logging.getLogger(__name__)
base_url = str(Cfg().network.proxy_free[CrawlerID.avsox])


def parse_spa(movie: MovieInfo):
    """Use the current site's own search and detail endpoints."""
    origin = base_url.rstrip('/') + '/'
    timeout = Cfg().network.timeout.total_seconds()
    with requests.Session() as session:
        session.proxies.update(read_proxy())
        response = session.get(origin, timeout=timeout)
        response.raise_for_status()
        tokens = lxml_html.fromstring(response.content).xpath('//meta[@name="csrf-token"]/@content')
        if not tokens:
            raise WebsiteError('AVSOX: missing site request token')
        session.headers.update({'X-Requested-With': 'XMLHttpRequest',
                                'X-CSRF-Token': tokens[0], 'Referer': origin})

        def call(method, arguments):
            result = session.post(urljoin(origin, 'javu/data/api/' + method),
                                  json=arguments, timeout=timeout)
            result.raise_for_status()
            payload = result.json()
            if not isinstance(payload, dict) or payload.get('code') != 200:
                raise WebsiteError('AVSOX: unexpected API response')
            return payload.get('data')

        avid = movie.dvdid.upper()
        lookup = avid.replace('FC2-', 'FC2-PPV-', 1) if avid.startswith('FC2-') else avid
        results = call('search', [{'search': lookup, 'lang': 'tw'}, 60, 1])
        if not isinstance(results, list):
            raise WebsiteError('AVSOX: unexpected search result')
        matches = [item for item in results if isinstance(item, dict)
                   and str(item.get('movieFanHao', '')).upper() == lookup]
        if not matches:
            raise MovieNotFoundError(__name__, movie.dvdid)
        if len(matches) != 1:
            raise MovieDuplicateError(__name__, movie.dvdid, len(matches))
        movie_id = matches[0].get('movieId')
        if not movie_id:
            raise WebsiteError('AVSOX: search result lacks an identifier')
        data = call('getMovie', [movie_id, 'tw'])
        if not isinstance(data, dict) or str(data.get('movieFanHao', '')).upper() != lookup:
            raise WebsiteError('AVSOX: detail response did not match the requested number')

    movie.dvdid = avid
    movie.url = urljoin(origin, 'tw/movies/' + quote(str(movie_id), safe=''))
    movie.title = data.get('title') or data.get('title_tw') or data.get('title_ja')
    movie.cover = urljoin(origin, data['posterLarge']) if data.get('posterLarge') else None
    movie.publish_date = data.get('releaseDate') or None
    movie.duration = str(data['length']) if data.get('length') else None
    movie.producer = (data.get('studio') or {}).get('studioName')
    movie.serial = (data.get('series') or {}).get('seriesName')
    movie.genre = [item['genreName'] for item in (data.get('genre') or [])
                   if isinstance(item, dict) and item.get('genreName')]
    movie.actress = [item['starName'] for item in (data.get('star') or [])
                     if isinstance(item, dict) and item.get('starName')]


def parse_data(movie: MovieInfo):
    """解析指定番号的影片数据"""
    # avsox无法直接跳转到影片的网页，因此先搜索再从搜索结果中寻找目标网页
    full_id = movie.dvdid
    if full_id.startswith('FC2-'):
        full_id = full_id.replace('FC2-', 'FC2-PPV-')
    html = get_html(f'{base_url}tw/search/{full_id}')
    if html.xpath("//div[@id='javu-site-index']"):
        return parse_spa(movie)
    ids = html.xpath("//div[@class='photo-info']/span/date[1]/text()")
    urls = html.xpath("//a[contains(@class, 'movie-box')]/@href")
    ids_lower = list(map(str.lower, ids))
    if full_id.lower() in ids_lower:
        url = urls[ids_lower.index(full_id.lower())]
        url = url.replace('/tw/', '/cn/', 1)
    else:
        raise MovieNotFoundError(__name__, movie.dvdid, ids)

    # 提取影片信息
    html = get_html(url)
    container = html.xpath("/html/body/div[@class='container']")[0]
    title = container.xpath("h3/text()")[0]
    cover = container.xpath("//a[@class='bigImage']/@href")[0]
    info = container.xpath("div/div[@class='col-md-3 info']")[0]
    dvdid = info.xpath("p/span[@style]/text()")[0]
    publish_date = info.xpath("p/span[text()='发行时间:']")[0].tail.strip()
    duration = info.xpath("p/span[text()='长度:']")[0].tail.replace('分钟', '').strip()
    producer, serial = None, None
    producer_tag = info.xpath("p[text()='制作商: ']")[0].getnext().xpath("a")
    if producer_tag:
        producer = producer_tag[0].text_content()
    serial_tag = info.xpath("p[text()='系列:']")
    if serial_tag:
        serial = serial_tag[0].getnext().xpath("a/text()")[0]
    genre = info.xpath("p/span[@class='genre']/a/text()")
    actress = container.xpath("//a[@class='avatar-box']/span/text()")

    movie.dvdid = dvdid.replace('FC2-PPV-', 'FC2-')
    movie.url = url
    movie.title = title.replace(dvdid, '').strip()
    movie.cover = cover
    movie.publish_date = publish_date
    movie.duration = duration
    movie.genre = genre
    movie.actress = actress
    if full_id.startswith('FC2-'):
        # avsox把FC2作品的拍摄者归类到'系列'而制作商固定为'FC2-PPV'，这既不合理也与其他的站点不兼容，因此进行调整
        movie.producer = serial
    else:
        movie.producer = producer
        movie.serial = serial


if __name__ == "__main__":
    import pretty_errors
    pretty_errors.configure(display_link=True)
    logger.root.handlers[1].level = logging.DEBUG

    movie = MovieInfo('082713-417')
    try:
        parse_data(movie)
        print(movie)
    except CrawlerError as e:
        logger.error(e, exc_info=1)
