import re
from urllib.parse import quote, urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings()


class LogicFFMisse:
    BASE_URL = "https://misskon.com"
    API_PATH = "/wp-json/wp/v2/posts"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    }

    CATEGORY_PATHS = {
        "top3": "top3",
        "top7": "top7",
        "top30": "top30",
        "top60": "top60",
    }

    @staticmethod
    def get_session():
        try:
            from .setup import P
            proxy_url = P.ModelSetting.get("proxy_url")
        except Exception:
            proxy_url = None

        proxies = {}
        if proxy_url:
            proxies = {
                "http": proxy_url,
                "https": proxy_url
            }

        # cloudscraper 생성
        try:
            import cloudscraper

            session = cloudscraper.create_scraper(
                browser={
                    "browser": "chrome",
                    "platform": "windows",
                    "mobile": False,
                },
                delay=10
            )

        except Exception:
            session = requests.Session()

        # 헤더
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
            "Referer": "https://misskon.com/",
            "Origin": "https://misskon.com",
        })

        # Proxy
        if proxies:
            session.proxies.update(proxies)

        # SSL verify 사용
        session.verify = True

        # adapter
        from requests.adapters import HTTPAdapter

        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=3
        )

        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    @staticmethod
    def is_supported_base_url(url):
        parsed = urlparse(url or "")
        host = parsed.netloc.lower()
        return host == "ffmisse.com" or host.endswith(".ffmisse.com")

    @staticmethod
    def discover_url(url=None):
        return LogicFFMisse.BASE_URL

    @staticmethod
    def normalize_image_url(url):
        if not url:
            return ""
        url = url.replace("\\/", "/").replace("&amp;", "&").strip()
        if "," in url:
            url = url.split(",")[0].split(" ")[0]
        if url.startswith("//"):
            url = "https:" + url
        return url

    @staticmethod
    def get_list(base_url=None, page=1, search="", category=""):
        base_url = (base_url or LogicFFMisse.BASE_URL).rstrip("/")
        if not LogicFFMisse.is_supported_base_url(base_url):
            base_url = LogicFFMisse.BASE_URL

        if not category:
            try:
                items = LogicFFMisse._parse_api_list(base_url, page, search)
                if items:
                    return items
            except Exception as e:
                try:
                    from .setup import P
                    P.logger.error(f"[FFMisse] API List Error: {e}")
                except:
                    pass

        return LogicFFMisse.parse_html_list(base_url, page, search, category)

    @staticmethod
    def _parse_api_list(base_url, page=1, search=""):
        session = LogicFFMisse.get_session()
        params = {"page": page, "per_page": 20, "_embed": 1, "orderby": "date"}
        if search:
            params["search"] = search

        res = session.get(
            f"{base_url}{LogicFFMisse.API_PATH}",
            params=params,
            headers=LogicFFMisse.HEADERS,
            timeout=(10, 30),
        )
        if res.status_code != 200:
            return []

        results = []
        for post in res.json():
            thumb = LogicFFMisse._api_thumbnail(post)
            if not thumb:
                images = LogicFFMisse.extract_images_from_html(
                    post.get("content", {}).get("rendered", "")
                )
                thumb = images[0] if images else ""
            link = post.get("link", "")
            results.append(
                {
                    "id": post.get("id") or LogicFFMisse._id_from_url(link),
                    "title": BeautifulSoup(
                        post.get("title", {}).get("rendered", ""), "html.parser"
                    ).get_text(strip=True),
                    "url": link,
                    "thumbnail": LogicFFMisse.normalize_image_url(thumb),
                }
            )
        return results

    @staticmethod
    def _api_thumbnail(post):
        embedded = post.get("_embedded", {})
        media = embedded.get("wp:featuredmedia")
        if media and isinstance(media, list):
            return media[0].get("source_url", "")
        return ""

    @staticmethod
    def parse_html_list(base_url, page=1, search="", category=""):
        base_url = base_url.rstrip("/")
        urls = LogicFFMisse._list_urls(base_url, page, search, category)

        session = LogicFFMisse.get_session()
        res = None
        for url in urls:
            try:
                candidate = session.get(
                    url,
                    headers=LogicFFMisse.HEADERS,
                    timeout=(15, 60),
                    allow_redirects=True
                )
                if candidate.status_code == 200:
                    res = candidate
                    break
                else:
                    try:
                        from .setup import P
                        P.logger.error(f"[FFMisse] HTML List HTTP {candidate.status_code}: {url}")
                    except:
                        pass
            except Exception as e:
                try:
                    from .setup import P
                    P.logger.error(f"[FFMisse] HTML List Exception: {e} ({url})")
                except:
                    pass
                continue
        if not res:
            return []

        soup = BeautifulSoup(res.text, "html.parser")
        posts = soup.select(
            "article, .post, .type-post, .hentry, .entry, .td_module_wrap, .item"
        )
        if not posts:
            posts = soup.select("h2, h3")

        results = []
        for post in posts:
            item = LogicFFMisse._parse_list_item(post, base_url)
            if item and not any(row["url"] == item["url"] for row in results):
                results.append(item)
        return results

    @staticmethod
    def _list_urls(base_url, page=1, search="", category=""):
        if search:
            q = quote(search)
            if page > 1:
                return [
                    f"{base_url}/page/{page}/?s={q}",
                    f"{base_url}/?s={q}&paged={page}",
                    f"{base_url}/search/{q}/page/{page}/",
                ]
            return [f"{base_url}/?s={q}", f"{base_url}/search/{q}/"]

        path = LogicFFMisse.CATEGORY_PATHS.get(category, category).strip("/")
        if path:
            if page > 1:
                return [f"{base_url}/{path}/page/{page}/", f"{base_url}/{path}/?paged={page}"]
            return [f"{base_url}/{path}/"]

        if page > 1:
            return [f"{base_url}/page/{page}/"]
        return [f"{base_url}/"]

    @staticmethod
    def _parse_list_item(node, base_url):
        # We need the correct post link.
        # h1 a, h2 a, h3 a are usually the title.
        title_tag = node.select_one("h1 a[href], h2 a[href], h3 a[href], .entry-title a[href]")
        
        link_href = ""
        title = ""
        
        if title_tag:
            link_href = title_tag.get("href", "")
            title = title_tag.get_text(strip=True)
            
        if not link_href or not LogicFFMisse._is_post_url(urljoin(base_url + "/", link_href)):
            # Fallback: iterate all links and find the first one that is a post url.
            for a in node.select("a[href]"):
                href = a.get("href", "")
                if LogicFFMisse._is_post_url(urljoin(base_url + "/", href)):
                    link_href = href
                    if not title:
                        title = a.get("title", "").strip() or a.get_text(strip=True)
                    break
                    
        if not link_href:
            return None
            
        href = urljoin(base_url + "/", link_href)
        
        if not title:
            img = node.select_one("img")
            title = img.get("alt", "").strip() if img else ""
        if not title:
            return None

        img = node.select_one("img")
        thumb = LogicFFMisse._image_from_tag(img, base_url) if img else ""
        return {
            "id": LogicFFMisse._id_from_url(href),
            "title": title,
            "url": href,
            "thumbnail": thumb,
        }

    @staticmethod
    def _is_post_url(url):
        parsed = urlparse(url)
        if not LogicFFMisse.is_supported_base_url(url):
            return False
        path = parsed.path.strip("/")
        if not path or path.startswith(("page/", "category/", "tag/", "sets/", "author/")):
            return False
        return True

    @staticmethod
    def extract_images_from_html(html, base_url=None):
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        images = []
        for img in soup.select("img"):
            src = LogicFFMisse._image_from_tag(img, base_url)
            if src and src not in images:
                images.append(src)
        return images

    @staticmethod
    def _image_from_tag(img, base_url=None):
        src = (
            img.get("data-src")
            or img.get("data-lazy-src")
            or img.get("data-original")
            or img.get("data-full-url")
            or img.get("srcset")
            or img.get("src")
            or ""
        )
        src = LogicFFMisse.normalize_image_url(src)
        if base_url and src:
            src = urljoin(base_url + "/", src)
        return src

    @staticmethod
    def get_detail(url):
        try:
            session = LogicFFMisse.get_session()
            soup = LogicFFMisse._fetch_soup(session, url)
            if not soup:
                return None
            title_tag = soup.select_one(
                "h1.entry-title, .entry-title, h1.post-title, h1"
            )
            title = title_tag.get_text(strip=True) if title_tag else ""

            data = {"title": title, "images": [], "videos": [], "downloads": []}
            page_urls = LogicFFMisse._collect_detail_page_urls(soup, url)
            page_soups = {url: soup}
            index = 0
            while index < len(page_urls):
                page_url = page_urls[index]
                page_soup = page_soups.get(page_url)
                if not page_soup:
                    page_soup = LogicFFMisse._fetch_soup(session, page_url)
                    if page_soup:
                        page_soups[page_url] = page_soup
                if page_soup:
                    for discovered in LogicFFMisse._collect_detail_page_urls(page_soup, url):
                        if discovered not in page_urls:
                            page_urls.append(discovered)
                    page_urls = sorted(page_urls, key=LogicFFMisse._detail_page_sort_key)
                index += 1

            for page_url in page_urls:
                page_soup = soup if page_url == url else LogicFFMisse._fetch_soup(session, page_url)
                if not page_soup:
                    continue
                content = page_soup.select_one(
                    ".entry-content, .post-content, .td-post-content, article, main"
                ) or page_soup.body
                if not content:
                    continue

                for img_url in LogicFFMisse.extract_images_from_html(str(content), page_url):
                    if LogicFFMisse._is_content_image(img_url) and img_url not in data["images"]:
                        data["images"].append(img_url)

                for iframe in content.select("iframe"):
                    src = urljoin(page_url, iframe.get("src", ""))
                    if src and src not in data["videos"]:
                        data["videos"].append(src)

                for video in content.select("video source, video"):
                    src = urljoin(page_url, video.get("src", ""))
                    if src and src not in data["videos"]:
                        data["videos"].append(src)

                for a in content.select("a[href]"):
                    href = urljoin(page_url, a.get("href", ""))
                    if LogicFFMisse._is_download_link(href):
                        if not any(row["link"] == href for row in data["downloads"]):
                            data["downloads"].append(
                                {"name": a.get_text(strip=True) or "Download Link", "link": href}
                            )

            return data
        except Exception as e:
            print(f"[FFMisse] get_detail error: {type(e).__name__}: {e}")
            return None

    @staticmethod
    def _fetch_soup(session, url):
        try:
            res = session.get(url, headers=LogicFFMisse.HEADERS, timeout=(10, 30))
            if res.status_code == 200:
                return BeautifulSoup(res.text, "html.parser")
            else:
                try:
                    from .setup import P
                    P.logger.error(f"[FFMisse] Detail fetch HTTP {res.status_code}: {url}")
                except:
                    pass
        except Exception as e:
            try:
                from .setup import P
                P.logger.error(f"[FFMisse] Detail fetch exception: {e} ({url})")
            except:
                pass
        return None

    @staticmethod
    def _collect_detail_page_urls(soup, url):
        urls = [url]
        selectors = [
            ".page-links a[href]",
            ".post-page-numbers",
            ".pagination a[href]",
        ]
        for selector in selectors:
            for tag in soup.select(selector):
                href = urljoin(url, tag.get("href", ""))
                if href:
                    href = href.split('#')[0]
                    if LogicFFMisse.is_supported_base_url(href) and href not in urls:
                        urls.append(href)
        return sorted(urls, key=LogicFFMisse._detail_page_sort_key)

    @staticmethod
    def _detail_page_sort_key(url):
        path = urlparse(url).path.rstrip("/")
        last = path.split("/")[-1]
        return int(last) if last.isdigit() else 1

    @staticmethod
    def _is_content_image(url):
        lowered = url.lower()
        if not lowered.startswith(("http://", "https://")):
            return False
        if any(token in lowered for token in ["avatar", "logo", "blank", "loading", "thumbnail"]):
            return False
        return bool(re.search(r"\.(jpe?g|png|webp|gif)(\?|$)", lowered))

    @staticmethod
    def _is_download_link(url):
        host = urlparse(url).netloc.lower()
        if not host:
            return False
        if host == "ffmisse.com" or host.endswith(".ffmisse.com"):
            return False
        providers = [
            "mediafire",
            "mega.nz",
            "terabox",
            "pixeldrain",
            "gofile",
            "drive.google",
            "dropbox",
            "katfile",
            "rapidgator",
            "send.cm",
        ]
        return any(provider in host for provider in providers)

    @staticmethod
    def _id_from_url(url):
        path = urlparse(url).path.strip("/")
        return path.split("/")[-1] if path else url


if __name__ == "__main__":
    items = LogicFFMisse.get_list(page=1)
    for item in items[:3]:
        print(item["title"], item["url"], item["thumbnail"])
