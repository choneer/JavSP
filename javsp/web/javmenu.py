"""从JavMenu抓取数据"""
import logging
from urllib.parse import urljoin

from javsp.web.base import Request, resp2html
from javsp.web.exceptions import *
from javsp.datatype import MovieInfo


request = Request()

logger = logging.getLogger(__name__)
base_url = 'https://mrzyx.xyz'


def parse_data(movie: MovieInfo):
    """从网页抓取并解析指定番号的数据
    Args:
        movie (MovieInfo): 要解析的影片信息，解析后的信息直接更新到此变量内
    """
    # JavMenu网页做得很不走心，将就了
    url = f'{base_url}/{movie.dvdid}'
    r = request.get(url)
    if r.history:
        # 被重定向到主页说明找不到影片资源
        raise MovieNotFoundError(__name__, movie.dvdid)

    html = resp2html(r)
    title_nodes = html.xpath("//h1/strong")
    if not title_nodes:
        raise WebsiteError("JavMenu: missing title; page layout may have changed")
    title = title_nodes[0].text_content().strip()
    title = title.replace('  | JAV目錄大全 | 每日更新', '')
    title = title.replace('免費在線看', '').replace('免費AV在線看', '')
    cover = html.xpath("//meta[@property='og:image']/@content")
    if not cover:
        cover = html.xpath("//video/@data-poster | //img[contains(@class,'lazy')]/@data-src")
    if cover:
        movie.cover = urljoin(r.url, cover[0].strip())
    info_nodes = html.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' card-body ')]")
    info = info_nodes[0] if info_nodes else html

    def info_value(*labels):
        for label in labels:
            nodes = info.xpath(".//div/span[contains(normalize-space(.), $label)]/following-sibling::span[1]", label=label)
            if nodes:
                return nodes[0].text_content().strip()
        return None

    publish_date = info_value('日期:', '發佈於:')
    duration = info_value('時長:')
    if duration:
        duration = duration.replace('分鐘', '').strip()
    producer = info.xpath(".//div/span[contains(text(), '製作:')]/following-sibling::a/span/text()")
    if producer:
        movie.producer = producer[0].strip()
    genre_tags = info.xpath(".//a[contains(concat(' ', normalize-space(@class), ' '), ' genre ')]")
    genre, genre_id = [], []
    for tag in genre_tags:
        items = tag.get('href').split('/')
        pre_id = items[-3] + '/' + items[-1]
        genre.append(tag.text.strip())
        genre_id.append(pre_id)
        # genre的链接中含有censored字段，但是无法用来判断影片是否有码，因为完全不可靠……
    actress = info.xpath(".//div/span[contains(text(), '女優:')]/following-sibling::*/a/text()") or None
    magnet_table = html.xpath("//table[contains(@class, 'magnet-table')]/tbody")
    if magnet_table:
        magnet_links = magnet_table[0].xpath("tr/td/a/@href")
        # 它的FC2数据是从JavDB抓的，JavDB更换图片服务器后它也跟上了，似乎数据更新频率还可以
        movie.magnet = [i.replace('[javdb.com]','') for i in magnet_links]
    preview_pics = [urljoin(r.url, item) for item in html.xpath("//a[@data-fancybox='gallery']/@href")]

    if (not movie.cover) and preview_pics:
        movie.cover = preview_pics[0]
    movie.url = r.url
    movie.title = title.replace(movie.dvdid, '').strip()
    movie.preview_pics = preview_pics
    movie.publish_date = publish_date
    movie.duration = duration
    movie.genre = genre
    movie.genre_id = genre_id
    movie.actress = actress


if __name__ == "__main__":
    import pretty_errors
    pretty_errors.configure(display_link=True)
    logger.root.handlers[1].level = logging.DEBUG

    movie = MovieInfo('FC2-718323')
    try:
        parse_data(movie)
        print(movie)
    except CrawlerError as e:
        logger.error(e, exc_info=1)
