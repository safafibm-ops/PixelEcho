"""Bounded public-page evidence collection for stage 2.

Adapted workflow: UKPLab/5pils dataset_collection/scrape_utils.py,
find_image_caption and extract_info_trafilatura (Apache-2.0).
This implementation uses explicit image URL associations and a guarded fetcher;
it does not execute the upstream requests-based scraper or infer provenance.
"""

import asyncio
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import re
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
import httpx
import trafilatura

USER_AGENT = 'TraceImageResearch/0.2'
MAX_HTML_BYTES = 1_000_000
MAX_REDIRECTS = 3
MAX_PAGES = 5
MAX_TEXT = 12_000


class EvidenceError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message
        super().__init__(message)


def is_public_address(value):
    address = ipaddress.ip_address(value)
    return address.is_global and not address.is_multicast and not address.is_reserved


def validate_url(value):
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
        if (parsed.scheme not in ('http', 'https') or not host or
                parsed.username or parsed.password or '%' in host or
                '\\' in value or any(ord(c) < 32 or ord(c) == 127 for c in value) or
                port not in (None, 80 if parsed.scheme == 'http' else 443)):
            raise ValueError('Unsafe URL')
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and not is_public_address(host):
            raise ValueError('Non-public IP')
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or '/', parsed.query, ''))
    except (TypeError, ValueError):
        raise EvidenceError('blocked', 'Only public HTTP or HTTPS pages on standard ports can be collected.') from None


async def resolve_public(url):
    parsed = urlsplit(validate_url(url))
    try:
        records = await asyncio.get_running_loop().getaddrinfo(
            parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80),
            type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        raise EvidenceError('unavailable', 'The source hostname could not be resolved.') from None
    addresses = list(dict.fromkeys(record[4][0] for record in records))
    # Reject mixed public/private answers, not just whichever address is first.
    if not addresses or any(not is_public_address(ip) for ip in addresses):
        raise EvidenceError('blocked', 'The source does not resolve exclusively to public addresses.')
    return addresses


class SafeFetcher:
    def __init__(self, *, transport=None, resolver=None):
        self.transport = transport
        self.resolver = resolver or resolve_public
        self.robots_cache = {}
        self.robots_lock = asyncio.Lock()

    async def _once(self, url, *, robots=False, image=False):
        addresses = await self.resolver(url)
        # Pin the actual connection to an address already checked above. Keep
        # the original HTTP Host and TLS SNI for certificate verification.
        target = httpx.URL(url)
        address = addresses[0]
        if not is_public_address(address):
            raise EvidenceError('blocked', 'The connection address is not public.')
        pinned = target.copy_with(host=address)
        headers = {'Host': target.netloc.decode('ascii'), 'User-Agent': USER_AGENT,
                   'Accept': 'text/plain' if robots else ('image/jpeg,image/png,image/webp' if image else 'text/html,application/xhtml+xml')}
        limit = 128_000 if robots else (5_000_000 if image else MAX_HTML_BYTES)
        try:
            # A fresh client avoids sharing a pinned-IP TLS connection between
            # different hostnames. Environment proxies and cookies are not used.
            async with httpx.AsyncClient(transport=self.transport, timeout=6,
                                         trust_env=False, follow_redirects=False) as client:
                async with client.stream('GET', pinned, headers=headers,
                                         extensions={'sni_hostname': target.raw_host.decode('ascii')}) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        return response.status_code, response.headers.get('location'), ''
                    if response.status_code != 200:
                        return response.status_code, None, ''
                    content_type = response.headers.get('content-type', '').split(';')[0].strip().lower()
                    allowed = ('image/jpeg', 'image/png', 'image/webp') if image else ('text/html', 'application/xhtml+xml')
                    if not robots and content_type not in allowed:
                        raise EvidenceError('unsupported', 'This source has an unsupported content type.')
                    try:
                        if int(response.headers.get('content-length', '0')) > limit:
                            raise EvidenceError('too_large', 'The source exceeds the collection size limit.')
                    except ValueError:
                        pass
                    content = bytearray()
                    async for part in response.aiter_bytes(chunk_size=16_384):
                        if len(content) + len(part) > limit:
                            raise EvidenceError('too_large', 'The source exceeds the collection size limit.')
                        content.extend(part)
                    return 200, None, bytes(content) if image else bytes(content).decode(response.encoding or 'utf-8', errors='replace')
        except httpx.TimeoutException:
            raise EvidenceError('timeout', 'The source timed out.') from None
        except httpx.HTTPError:
            raise EvidenceError('unavailable', 'The source could not be downloaded securely.') from None

    async def fetch(self, url, *, robots=False, image=False):
        current = validate_url(url)
        for hop in range(MAX_REDIRECTS + 1):
            if not robots:
                await self.check_robots(current)
            code, location, content = await self._once(current, robots=robots, image=image)
            if code in (301, 302, 303, 307, 308):
                if not location or hop == MAX_REDIRECTS:
                    raise EvidenceError('unavailable', 'The source redirected too many times or omitted its destination.')
                current = validate_url(urljoin(current, location))
                continue
            return code, current, content

    async def check_robots(self, url):
        parsed = urlsplit(url)
        origin = f'{parsed.scheme}://{parsed.netloc}'
        async with self.robots_lock:
            if origin not in self.robots_cache:
                code, _, text = await self.fetch(origin + '/robots.txt', robots=True)
                if code in (404, 410):
                    policy = None
                elif code == 200:
                    policy = RobotFileParser()
                    policy.parse(text.splitlines())
                else:
                    raise EvidenceError('blocked', 'The source robots policy is unavailable or denies access.')
                self.robots_cache[origin] = policy
        policy = self.robots_cache[origin]
        if policy is not None and not policy.can_fetch(USER_AGENT, url):
            raise EvidenceError('blocked', 'The source robots policy does not permit collecting this page.')


def clean(value, limit=1000):
    return re.sub(r'\s+', ' ', str(value or '')).strip()[:limit]


def image_key(value, base):
    try:
        parsed = urlsplit(urljoin(base, value))
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            return None
        # Preserve query parameters: differing image URLs may be different photos.
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ''))
    except (ValueError, TypeError):
        return None


def image_sources(tag, base):
    sources = set()
    for attr in ('src', 'data-src', 'data-original', 'data-lazy-src'):
        if tag.get(attr):
            sources.add(image_key(tag[attr], base))
    for attr in ('srcset', 'data-srcset'):
        for item in tag.get(attr, '').split(','):
            parts = item.strip().split()
            if parts:
                sources.add(image_key(parts[0], base))
    parent = tag.parent
    if tag.name == 'img' and parent and parent.name == 'picture':
        for source in parent.find_all('source'):
            sources.update(image_sources(source, base))
    sources.discard(None)
    return sources


def associated_image(tag, image_url):
    figure = tag.find_parent('figure')
    # Do not use a broad article/body ancestor to borrow another image's caption.
    scope = figure or (tag.parent if tag.parent and tag.parent.name not in ('body', 'html', 'article', 'main') else None)
    caption = figure.find('figcaption') if figure else None
    if caption is None and scope and len(scope.find_all('img')) <= 3:
        caption = scope.find(class_=re.compile(r'(^|[-_\s])caption($|[-_\s])', re.I))
    credit = None
    if scope and (figure or len(scope.find_all('img')) <= 3):
        credit = scope.find(attrs={'itemprop': re.compile(r'^(creditText|copyrightNotice)$')})
        if credit is None:
            credit = scope.find(class_=re.compile(r'(^|[-_\s])(credits?|attribution)($|[-_\s])', re.I))
    caption_text = clean(caption.get_text(' ', strip=True)) if caption else None
    credit_text = clean(credit.get_text(' ', strip=True)) if credit else None
    if not credit_text and caption_text:
        match = re.search(r'\b(?:photo(?:graph)?(?:\s+credit)?|image\s+credit|credit)\s*[:©]\s*(.{1,180})', caption_text, re.I)
        if match:
            credit_text = clean(match.group(0), 200)
    return {'image_url': image_url, 'association': 'image_element_located',
            'caption': caption_text, 'reported_credit': credit_text,
            'alt_text': clean(tag.get('alt')) or None,
            'association_method': 'exact_image_url_in_dom',
            'visual_verification': 'pending'}


def extract_page(html, page_url, image_urls):
    soup = BeautifulSoup(html, 'html.parser')
    article_author = None
    dates = []
    image_metadata = []
    description = None
    for meta in soup.find_all('meta'):
        name = str(meta.get('property') or meta.get('name') or '').lower()
        value = clean(meta.get('content'))
        if name == 'author' and value:
            article_author = value
        if name in ('description', 'og:description') and value and not description:
            description = value
        kind = {'article:published_time': 'page_publication_date',
                'article:modified_time': 'page_modified_date'}.get(name)
        if kind and value:
            dates.append({'value': value, 'type': kind, 'source': f'meta:{name}'})
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            raw = json.loads(script.string or '')
        except (ValueError, TypeError):
            continue
        nodes = raw if isinstance(raw, list) else [raw]
        for entry in list(nodes):
            if isinstance(entry, dict) and isinstance(entry.get('@graph'), list):
                nodes.extend(entry['@graph'])
        for entry in nodes[:100]:
            if not isinstance(entry, dict):
                continue
            types = entry.get('@type', [])
            if isinstance(types, str):
                types = [types]
            if isinstance(types, list) and 'ImageObject' in types:
                object_urls = [entry.get(field) for field in ('contentUrl', 'url', '@id') if isinstance(entry.get(field), str)]
                for known_url in image_urls:
                    if not any(image_key(value, page_url) == image_key(known_url, page_url) for value in object_urls):
                        continue
                    creator = entry.get('creator')
                    if isinstance(creator, dict):
                        creator = creator.get('name')
                    location = entry.get('contentLocation')
                    if isinstance(location, dict):
                        location = location.get('name')
                    image_metadata.append({'image_url': known_url,
                        'creator': clean(creator, 200) if isinstance(creator, str) else None,
                        'location': clean(location, 200) if isinstance(location, str) else None,
                        'date_created': clean(entry['dateCreated'], 120) if isinstance(entry.get('dateCreated'), str) else None,
                        'caption': clean(entry['caption']) if isinstance(entry.get('caption'), str) else None,
                        'source': 'jsonld:ImageObject'})
            if not isinstance(types, list) or not any(t in ('Article', 'NewsArticle', 'BlogPosting') for t in types):
                continue
            for field, kind in [('datePublished', 'page_publication_date'), ('dateModified', 'page_modified_date')]:
                if isinstance(entry.get(field), str):
                    dates.append({'value': clean(entry[field], 120), 'type': kind, 'source': f'jsonld:{field}'})
    associations = []
    tags = [(tag, image_sources(tag, page_url)) for tag in soup.find_all('img')]
    for value in dict.fromkeys(image_urls):
        expected = image_key(value, page_url)
        tag = next((tag for tag, sources in tags if expected and expected in sources), None)
        associations.append(associated_image(tag, value) if tag else {
            'image_url': value, 'association': 'image_element_not_located',
            'caption': None, 'reported_credit': None, 'alt_text': None,
            'association_method': None, 'visual_verification': 'pending'})
    title = clean(soup.title.get_text(' ', strip=True), 500) if soup.title else None
    # Main article extraction follows the selected 5Pils workflow, using the
    # current text API instead of its old bare_extraction dictionary contract.
    text = trafilatura.extract(html, include_comments=False, include_tables=False,
                               favor_precision=True, fast=True, url=page_url) or ''
    method = 'trafilatura'
    if not text:
        for unwanted in soup.select('script,style,nav,footer,header,aside,form,noscript'):
            unwanted.decompose()
        article = soup.find('article') or soup.find('main')
        text = '\n'.join(tag.get_text(' ', strip=True) for tag in article.find_all('p')) if article else ''
        method = 'article_paragraphs' if text else 'no_article_text'
    dates = list({(d['value'], d['type'], d['source']): d for d in dates}.values())
    return {'title': title, 'article_author': article_author, 'description': description,
            'page_dates': dates, 'image_associations': associations,
            'image_metadata': image_metadata,
            'text': text[:MAX_TEXT], 'text_truncated': len(text) > MAX_TEXT,
            'text_method': method,
            'note': 'Page statements and DOM associations only. Article authors are not assumed to be photographers; page dates are not capture dates. Visual verification is pending.'}


async def collect_evidence(pages, *, fetcher=None):
    fetcher = fetcher or SafeFetcher()
    semaphore = asyncio.Semaphore(3)
    unique = {}
    for page in pages[:MAX_PAGES]:
        key = page['url'].split('#')[0]
        if key not in unique:
            unique[key] = {'url': key, 'image_urls': list(page.get('image_urls', []))}
        else:
            unique[key]['image_urls'].extend(page.get('image_urls', []))

    async def collect(page):
        record = {'id': hashlib.sha256(page['url'].encode()).hexdigest()[:12],
                  'requested_url': page['url'], 'final_url': None,
                  'retrieved_at': datetime.now(timezone.utc).isoformat(),
                  'status': 'unavailable'}
        try:
            async with semaphore, asyncio.timeout(12):
                code, final_url, html = await fetcher.fetch(page['url'])
                if code != 200:
                    raise EvidenceError('blocked' if code in (401, 403, 429) else 'unavailable',
                                        f'The source returned HTTP {code}.')
                parsed = await asyncio.to_thread(extract_page, html, final_url, page.get('image_urls', [])[:20])
            record.update(parsed)
            record.update(status='collected', final_url=final_url)
        except EvidenceError as error:
            record.update(status=error.status, message=error.message)
        except TimeoutError:
            record.update(status='timeout', message='Collection exceeded the per-page time limit.')
        except Exception:
            # Never leak remote response bodies, transport details, or secrets.
            record.update(status='unavailable', message='This source could not be processed.')
        return record

    records = await asyncio.gather(*(collect(page) for page in unique.values()))
    return {'pages': records, 'collected': sum(r['status'] == 'collected' for r in records),
            'attempted': len(records), 'max_pages': MAX_PAGES,
            'notice': 'Evidence is collected from public pages, not independently verified. Missing fields remain unknown.'}

