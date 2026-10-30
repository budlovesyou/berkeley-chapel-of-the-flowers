"""Best-effort artwork discovery from public event pages, never general image search."""
from datetime import datetime, timedelta
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, unquote, urljoin
from urllib.request import Request, HTTPRedirectHandler, build_opener
from zoneinfo import ZoneInfo
import hashlib
import json
import re
import subprocess
import sys
import warnings

ZONE = ZoneInfo('America/Los_Angeles')
PAGE_HOSTS = {'eventbrite.com', 'www.eventbrite.com', 'partiful.com', 'www.partiful.com', 'lu.ma', 'luma.com', 'www.luma.com'}
IMAGE_HOSTS = {'img.evbuc.com', 'cdn.evbuc.com', 'partiful.imgix.net', 'images.lumacdn.com', 'cdn.lu.ma'}
LIMITS = {'page': 2_000_000, 'image': 8_000_000}
MAX_EVENTS = 5
WORKER_SECONDS = 45


def allowed_url(url, kind):
    try:
        p = urlsplit(url)
        if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
            return False
        if kind == 'image':
            return p.hostname in IMAGE_HOSTS and not re.search(r'(?:avatar|default|logo)', p.path, re.I)
        if p.hostname not in PAGE_HOSTS:
            return False
        if p.hostname in {'eventbrite.com', 'www.eventbrite.com'}:
            return bool(re.fullmatch(r'/e/[\w-]+-\d+/?', p.path))
        if 'partiful.com' in p.hostname:
            return bool(re.fullmatch(r'/e/[A-Za-z0-9]+/?', p.path))
        return bool(re.fullmatch(r'/[A-Za-z0-9_-]+/?', p.path))
    except (TypeError, ValueError):
        return False


class SafeRedirect(HTTPRedirectHandler):
    def __init__(self, kind):
        self.kind = kind

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl, self.kind):
            raise ValueError('Unsupported artwork redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_public(url, kind):
    if not allowed_url(url, kind):
        raise ValueError('Unsupported artwork URL')
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; ChapelPublicEvents/1.0)', 'Accept-Encoding': 'identity'})
    with build_opener(SafeRedirect(kind)).open(request, timeout=5) as response:
        data = response.read(LIMITS[kind] + 1)
        if len(data) > LIMITS[kind]:
            raise ValueError('Artwork response exceeds limit')
        return data, response.url


class Metadata(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.documents = []
        self.next_data = {}
        self.script = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            self.meta.setdefault(attrs.get('property', attrs.get('name', '')), attrs.get('content', ''))
        if tag == 'script' and (attrs.get('type') == 'application/ld+json' or attrs.get('id') == '__NEXT_DATA__'):
            self.script = (attrs.get('id'), [])

    def handle_data(self, data):
        if self.script:
            self.script[1].append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.script:
            try:
                data = json.loads(''.join(self.script[1]))
                if self.script[0] == '__NEXT_DATA__':
                    self.next_data = data
                else:
                    self.documents.append(data)
            except (ValueError, RecursionError):
                pass
            self.script = None


def nested(value, *keys):
    for key in keys:
        value = value.get(key, {}) if isinstance(value, dict) else {}
    return value if isinstance(value, dict) else {}


def event_nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from event_nodes(item)
    elif isinstance(value, dict):
        types = value.get('@type', [])
        types = [types] if isinstance(types, str) else types
        if isinstance(types, list) and any(isinstance(t, str) and t.endswith('Event') for t in types):
            yield value
        for key in ('@graph', 'mainEntity'):
            yield from event_nodes(value.get(key))


def matching_name(a, b):
    a = re.findall(r'\w+', str(a).casefold())
    b = re.findall(r'\w+', str(b).casefold())
    if a == b and a:
        return True
    common = set(a) & set(b)
    return len(common) >= 3 and len(common) / max(len(set(a) | set(b)), 1) >= .7


def local_day(value):
    stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return (stamp.astimezone(ZONE) if stamp.tzinfo else stamp).date()


def same_listing(a, b):
    """Ignore tracking parameters and Eventbrite's editable slug, but not event IDs."""
    a, b = urlsplit(a), urlsplit(b)
    if a.hostname in {'eventbrite.com', 'www.eventbrite.com'} and b.hostname in {'eventbrite.com', 'www.eventbrite.com'}:
        return a.path.rstrip('/').rsplit('-', 1)[-1] == b.path.rstrip('/').rsplit('-', 1)[-1]
    return a.hostname == b.hostname and a.path.rstrip('/') == b.path.rstrip('/')


def image_urls(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from image_urls(item)
    elif isinstance(value, dict):
        yield from image_urls(value.get('contentUrl') or value.get('url'))


def original_image(url, page_url):
    url = urljoin(page_url, url)
    for _ in range(3):
        p = urlsplit(url)
        if p.hostname in {'www.eventbrite.com', 'eventbrite.com'} and p.path == '/e/_next/image':
            url = parse_qs(p.query).get('url', [''])[0]
        elif p.hostname == 'img.evbuc.com':
            url = unquote(p.path.lstrip('/'))
        else:
            break
    return url if allowed_url(url, 'image') else None


def candidates(html, page_url, event):
    if not allowed_url(page_url, 'page'):
        return []
    metadata = Metadata(html)
    records = [record for doc in metadata.documents for record in event_nodes(doc)]
    host = urlsplit(page_url).hostname
    if host in {'partiful.com', 'www.partiful.com'}:
        record = nested(metadata.next_data, 'props', 'pageProps', 'event')
        if record.get('id') == urlsplit(page_url).path.strip('/').split('/')[-1]:
            records.append({'name': record.get('title'), 'startDate': record.get('startDate'), 'image': metadata.meta.get('og:image')})
    elif host in {'lu.ma', 'luma.com', 'www.luma.com'}:
        record = nested(metadata.next_data, 'props', 'pageProps', 'initialData', 'data', 'event')
        if record.get('url') == urlsplit(page_url).path.strip('/'):
            records.append({'name': record.get('name'), 'startDate': record.get('start_at'), 'image': record.get('cover_url') or metadata.meta.get('og:image')})
    result = []
    for record in records:
        if not matching_name(record.get('name', ''), event['title']):
            continue
        if record.get('url') and not same_listing(record['url'], page_url):
            continue
        if str(record.get('eventStatus', '')).endswith(('EventCancelled', 'EventPostponed')):
            continue
        try:
            day = local_day(record['startDate'])
            if day != local_day(event['start']):
                continue
            # Long series landing pages often replace their poster between dates.
            if record.get('endDate') and (local_day(record['endDate']) - day).days > 7:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        for raw in image_urls(record.get('image') or metadata.meta.get('og:image')):
            url = original_image(raw, page_url)
            if url and url not in result:
                result.append(url)
    return result[:3]


def optimize(data):
    from PIL import Image, ImageOps, UnidentifiedImageError
    if len(data) > LIMITS['image']:
        raise ValueError('Image response exceeds limit')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=['JPEG', 'PNG', 'WEBP']) as original:
                width, height = original.size
                if width < 300 or height < 150 or width * height > 20_000_000:
                    raise ValueError('Artwork dimensions outside limits')
                image = ImageOps.exif_transpose(original).convert('RGB')
                image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                output = BytesIO()
                image.save(output, format='WEBP', quality=84, method=6)
                return output.getvalue(), image.width, image.height
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError('Invalid artwork image') from error


def image_key(event):
    return 'occurrence:' + hashlib.sha256(json.dumps([event['uid'], str(event['start'])]).encode()).hexdigest()[:32]


def fingerprint(event):
    return hashlib.sha256(json.dumps([event['title'], str(event['start']), event['links']], sort_keys=True).encode()).hexdigest()


def read_manifest(root):
    path = root / 'event-images.json'
    return json.loads(path.read_text()) if path.exists() else {'version': 1, 'events': {}}


def valid_asset(image, root):
    if not isinstance(image, dict) or not re.fullmatch(r'assets/event-images/[a-z0-9-]+\.(?:webp|jpg|png)', str(image.get('src', ''))):
        return False
    return all(type(image.get(k)) is int and image[k] > 0 for k in ('width', 'height')) and (root / image['src']).is_file()


def load_images(events, root):
    manifest = read_manifest(root)
    result = {uid: image for uid, image in manifest.get('events', {}).items() if valid_asset(image, root)}
    for event in events:
        key = image_key(event)
        image = manifest.get('occurrences', {}).get(key)
        if valid_asset(image, root) and image.get('fingerprint') == fingerprint(event):
            result[key] = image
    return result


def save_manifest(root, manifest):
    path = root / 'event-images.json'
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def discover(events, root, now=None, reader=read_public):
    now = now or datetime.now(ZONE)
    manifest = read_manifest(root)
    attempts = manifest.setdefault('attempts', {})
    automatic = manifest.setdefault('occurrences', {})
    visited = set()
    tried = added = 0
    # Upcoming events first, then history. A batch cannot hold up the feed.
    events = sorted(events, key=lambda e: (str(e['end']) < str(now), str(e['start'])))
    for event in events:
        key, signature = image_key(event), fingerprint(event)
        if key in visited:
            continue
        visited.add(key)
        if event['uid'] in manifest.get('events', {}):
            continue  # Even a temporarily missing manual asset remains the user's choice.
        if valid_asset(automatic.get(key), root) and automatic[key].get('fingerprint') == signature:
            continue
        links = [url for url in event['links'] if allowed_url(url, 'page')][:3]
        if not links:
            continue
        previous = attempts.get(key, {})
        if previous.get('fingerprint') == signature:
            try:
                if now - datetime.fromisoformat(previous['checked_at']) < timedelta(days=1):
                    continue
            except (KeyError, ValueError, TypeError):
                pass
        if tried >= MAX_EVENTS:
            break
        tried += 1
        # Persist before network work. A hard timeout cannot starve the next batch.
        attempts[key] = {'fingerprint': signature, 'checked_at': now.isoformat(), 'outcome': 'pending'}
        save_manifest(root, manifest)
        selected = None
        for link in links:
            try:
                data, final_url = reader(link, 'page')
                urls = candidates(data.decode('utf-8', errors='replace'), final_url, event)
            except Exception:
                continue
            for url in urls:
                try:
                    data, final_image = reader(url, 'image')
                    if not allowed_url(final_image, 'image'):
                        continue
                    data, width, height = optimize(data)
                    name = hashlib.sha256(data).hexdigest()[:24] + '.webp'
                    path = root / 'assets/event-images' / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix('.webp.tmp')
                    temporary.write_bytes(data)
                    temporary.replace(path)
                    selected = {'src': 'assets/event-images/' + name, 'width': width, 'height': height,
                                'alt': 'Event artwork for ' + event['title'], 'source_url': final_url,
                                'original_url': final_image, 'discovered_on': now.date().isoformat(),
                                'fingerprint': signature}
                    break
                except Exception:
                    continue
            if selected:
                break
        if selected:
            automatic[key] = selected
            added += 1
        attempts[key]['outcome'] = 'added' if selected else 'not_found'
        save_manifest(root, manifest)
    print(json.dumps({'image_lookups': tried, 'images_added': added}), flush=True)


def run_discovery(events, root):
    payload = json.dumps(events, default=str)
    try:
        subprocess.run([sys.executable, str(Path(__file__).resolve()), str(root)],
                       input=payload, text=True, timeout=WORKER_SECONDS, check=True)
    except (OSError, subprocess.SubprocessError) as error:
        print('Image discovery skipped; calendar publication continues (' + type(error).__name__ + ').', flush=True)


if __name__ == '__main__':
    discover(json.load(sys.stdin), Path(sys.argv[1]))
