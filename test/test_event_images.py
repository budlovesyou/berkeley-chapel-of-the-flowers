"""Behavior tests for optional public-event image enrichment."""
import io
import json
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
from unittest.mock import patch
from urllib.request import Request
from zoneinfo import ZoneInfo

from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import event_images as images

NOW = datetime(2026, 10, 30, 12, tzinfo=ZoneInfo('America/Los_Angeles'))
PAGE = 'https://www.eventbrite.com/e/public-concert-tickets-123456789'
ART = 'https://cdn.evbuc.com/images/concert.jpg'

def event(uid='new', **changes):
    value = dict(uid=uid, title='Public Concert at the Chapel',
                 start=NOW + timedelta(days=2), end=NOW + timedelta(days=2, hours=2),
                 links=[PAGE], description='', allDay=False, location='Berkeley')
    value.update(changes)
    return value

def page(name='Public Concert at the Chapel', start='2026-11-01T12:00:00-08:00', image=ART):
    return '<script type="application/ld+json">' + json.dumps({
        '@type': 'MusicEvent', 'name': name, 'startDate': start,
        'url': PAGE, 'image': image}) + '</script>'

def png(size=(600, 300)):
    data = io.BytesIO()
    Image.new('RGB', size, 'navy').save(data, format='PNG')
    return data.getvalue()

class MetadataTests(unittest.TestCase):
    def test_eventbrite_matching_event_and_uncropped_original(self):
        wrapped = 'https://www.eventbrite.com/e/_next/image?url=https%3A%2F%2Fimg.evbuc.com%2Fhttps%253A%252F%252Fcdn.evbuc.com%252Fimages%252Fconcert.jpg%3Fw%3D940'
        self.assertEqual(images.candidates(page(image=wrapped), PAGE, event()), [ART])

    def test_wrong_title_date_or_related_event_cannot_supply_artwork(self):
        for html in [page(name='Unrelated Party'), page(start='2025-11-01T12:00:00-08:00'),
                     page().replace('tickets-123456789', 'tickets-987654321'),
                     '<meta property="og:image" content="'+ART+'">']:
            self.assertEqual(images.candidates(html, PAGE, event()), [])

    def test_partiful_embedded_date_uses_berkeley_day(self):
        data = {'props': {'pageProps': {'event': {'id': 'abc123', 'title': event()['title'],
                                                'startDate': '2026-11-02T04:00:00Z'}}}}
        html = '<meta property="og:image" content="https://partiful.imgix.net/user/flyer">'
        html += '<script id="__NEXT_DATA__" type="application/json">'+json.dumps(data)+'</script>'
        self.assertEqual(images.candidates(html, 'https://partiful.com/e/abc123', event()),
                         ['https://partiful.imgix.net/user/flyer'])

    def test_luma_cover_from_event_data(self):
        data = {'props': {'pageProps': {'initialData': {'data': {'event': {
            'name': event()['title'], 'start_at': '2026-11-01T20:00:00Z',
            'url': 'concert', 'cover_url': 'https://images.lumacdn.com/event-covers/poster.jpg'}}}}}}
        html = '<script id="__NEXT_DATA__">'+json.dumps(data)+'</script>'
        self.assertEqual(images.candidates(html, 'https://luma.com/concert', event()),
                         ['https://images.lumacdn.com/event-covers/poster.jpg'])

    def test_unsupported_private_or_disguised_urls_and_redirects_rejected(self):
        bad = ['http://www.eventbrite.com/e/concert-123', 'https://127.0.0.1/a',
               'https://www.eventbrite.com.attacker.test/e/concert-123',
               'https://user:pass@www.eventbrite.com/e/concert-123',
               'https://www.eventbrite.com:444/e/concert-123',
               'https://www.eventbrite.com/o/organizer', 'https://luma.com/']
        for url in bad:
            self.assertFalse(images.allowed_url(url, 'page'), url)
        redirect = images.SafeRedirect('image')
        with self.assertRaises(ValueError):
            redirect.redirect_request(Request(ART), None, 302, '', {}, 'http://169.254.169.254/latest')
        self.assertEqual(images.candidates(page(image='https://evil.test/a.png'), PAGE, event()), [])

class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def read(self, url, kind):
        return (page().encode() if kind == 'page' else png(), url)

    def test_new_event_saves_webp_and_survives_a_second_refresh(self):
        e = event()
        images.discover([e], self.root, NOW, self.read)
        manifest = json.loads((self.root/'event-images.json').read_text())
        self.assertEqual(manifest['events'], {})
        art = images.load_images([e], self.root)[images.image_key(e)]
        with Image.open(self.root/art['src']) as decoded:
            self.assertEqual(decoded.format, 'WEBP')
            self.assertEqual(decoded.size, (600, 300))
        self.assertEqual(art['source_url'], PAGE)
        def forbidden(*_): self.fail('Saved image should not be fetched again')
        images.discover([e], self.root, NOW+timedelta(minutes=15), forbidden)
        self.assertEqual(art, images.load_images([e], self.root)[images.image_key(e)])

    def test_manual_artwork_is_preserved_and_never_fetched(self):
        e = event(); target=self.root/'assets/event-images/manual.webp'; target.parent.mkdir(parents=True)
        target.write_bytes(png())
        original={'version':1,'events':{e['uid']:{'src':'assets/event-images/manual.webp','width':600,'height':300,'alt':'Chosen image'}}}
        (self.root/'event-images.json').write_text(json.dumps(original))
        def forbidden(*_): self.fail('Manual selection must be preserved')
        images.discover([e],self.root,NOW,forbidden)
        self.assertEqual(images.load_images([e],self.root)[e['uid']],original['events'][e['uid']])

    def test_recurrence_and_changed_title_do_not_reuse_dated_artwork(self):
        e=event(); later=event(start=e['start']+timedelta(days=7),end=e['end']+timedelta(days=7))
        images.discover([e,later],self.root,NOW,self.read)
        selected=images.load_images([e,later],self.root)
        self.assertIn(images.image_key(e),selected)
        self.assertNotIn(images.image_key(later),selected)
        changed=event(title='Different event')
        self.assertNotIn(images.image_key(changed),images.load_images([changed],self.root))

    def test_failure_is_cached_but_changed_link_and_next_day_retry(self):
        e=event(); calls=[]
        def failed(url,kind):calls.append(url);raise TimeoutError('Unavailable')
        images.discover([e],self.root,NOW,failed)
        self.assertEqual(images.load_images([e],self.root),{})
        images.discover([e],self.root,NOW+timedelta(hours=1),failed)
        self.assertEqual(len(calls),1)
        images.discover([e],self.root,NOW+timedelta(days=1),failed)
        self.assertEqual(len(calls),2)
        images.discover([event(links=[PAGE+'?changed=1'])],self.root,NOW+timedelta(days=1,minutes=1),failed)
        self.assertEqual(len(calls),3)

    def test_bad_first_source_and_image_do_not_block_second_source(self):
        first='https://www.eventbrite.com/e/bad-tickets-987654321'
        def read(url,kind):
            if url==first:raise OSError('gone')
            return self.read(url,kind)
        e=event(links=[first,PAGE]);images.discover([e],self.root,NOW,read)
        self.assertIn(images.image_key(e),images.load_images([e],self.root))
        bad=event('bad')
        images.discover([bad],self.root,NOW,lambda u,k:(page().encode() if k=='page' else b'<html>blocked</html>',u))
        self.assertNotIn(images.image_key(bad),images.load_images([bad],self.root))

    def test_batch_cap_and_attempt_checkpoint_prevent_starvation(self):
        es=[event(str(n)) for n in range(7)]
        def failed(url,kind):raise TimeoutError()
        images.discover(es,self.root,NOW,failed)
        state=json.loads((self.root/'event-images.json').read_text())
        self.assertEqual(len(state['attempts']),5)
        images.discover(es,self.root,NOW+timedelta(minutes=15),failed)
        state=json.loads((self.root/'event-images.json').read_text())
        self.assertEqual(len(state['attempts']),7)

    def test_invalid_and_oversized_images_rejected(self):
        for payload in [b'<svg></svg>',png((100,100)),png((5000,5000))]:
            with self.assertRaises(ValueError):images.optimize(payload)

    def test_failed_or_timed_out_worker_is_optional(self):
        import subprocess
        for error in [OSError('no worker'),subprocess.TimeoutExpired('worker',45),subprocess.CalledProcessError(1,'worker')]:
            with patch('event_images.subprocess.run',side_effect=error):
                images.run_discovery([event()],self.root)


class RenderingIntegrationTests(unittest.TestCase):
    def test_automatic_artwork_is_only_rendered_on_its_occurrence(self):
        from calendar_feed import render_page
        e=event(); later=event(start=e['start']+timedelta(days=7),end=e['end']+timedelta(days=7))
        art={'src':'assets/event-images/auto.webp','width':600,'height':300,'alt':'Poster'}
        html=render_page([e,later],'public@example.com',NOW,images={images.image_key(e):art})
        self.assertEqual(html.count('<img '),1)
        manual=dict(art,src='assets/event-images/manual.webp')
        html=render_page([e],'public@example.com',NOW,images={images.image_key(e):art,e['uid']:manual})
        self.assertIn('src="assets/event-images/manual.webp"',html)
        self.assertNotIn('src="assets/event-images/auto.webp"',html)


class FetchAndFailureTests(unittest.TestCase):
    def test_fetch_refuses_oversized_body(self):
        class Response(io.BytesIO):
            url=PAGE
        class Opener:
            def open(self,*args,**kwargs):return Response(b'x' * 2_000_001)
        with patch('event_images.build_opener',return_value=Opener()):
            with self.assertRaises(ValueError):images.read_public(PAGE,'page')

    def test_corrupt_first_image_tries_next_matching_image(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp); bad='https://cdn.evbuc.com/images/corrupt.jpg'
            def read(url,kind):
                if kind=='page':return page(image=[bad,ART]).encode(),url
                return (b'not an image' if url==bad else png()),url
            e=event();images.discover([e],root,NOW,read)
            self.assertEqual(images.load_images([e],root)[images.image_key(e)]['original_url'],ART)

    def test_cli_renders_calendar_despite_worker_timeout(self):
        import calendar_feed, subprocess
        from test_calendar_feed import feed, event as ics_event
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'assets').mkdir()
            (root/'assets/events.css').write_text('body{}')
            (root/'events.template.html').write_text('{{UPCOMING}}{{ARCHIVE}}')
            (root/'public-calendar.json').write_text(json.dumps({'calendarId':'public@example.com'}))
            source=root/'input.ics';source.write_bytes(feed(ics_event()))
            argv=['calendar_feed.py','--feed-file',str(source),'--discover-images']
            with patch('calendar_feed.ROOT',root),patch('sys.argv',argv),patch('event_images.subprocess.run',side_effect=subprocess.TimeoutExpired('worker',45)):
                calendar_feed.main()
            self.assertIn('Public Concert',(root/'events.html').read_text())
            self.assertEqual(len(list((root/'calendar').glob('*.ics'))),1)

if __name__=='__main__':unittest.main()
