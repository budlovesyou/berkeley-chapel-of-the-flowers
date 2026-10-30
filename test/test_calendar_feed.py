import unittest, sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from calendar_feed import parse_feed, render_page, fetch_verified, build_manifest
NOW=datetime(2026,10,30,12,tzinfo=ZoneInfo('America/Los_Angeles'))
def feed(events):return ('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Chapel test//EN\r\n'+events+'END:VCALENDAR\r\n').encode()
def event(uid='a',extra='',start='20261101T190000',end='20261101T210000'):
 return f'BEGIN:VEVENT\r\nUID:{uid}\r\nDTSTART;TZID=America/Los_Angeles:{start}\r\nDTEND;TZID=America/Los_Angeles:{end}\r\nSUMMARY:Public Concert\r\n{extra}END:VEVENT\r\n'
class CalendarFeedTests(unittest.TestCase):
 def test_privacy_and_malformed(self):
  items=parse_feed(feed(event()+event('p','CLASS:PRIVATE\r\n')+event('b').replace('SUMMARY:Public Concert','SUMMARY:Busy')+event('c','STATUS:CANCELLED\r\n')),NOW)
  self.assertEqual(len(items),1)
  with self.assertRaises(ValueError):parse_feed(b'<html>Login</html>',NOW)
 def test_recurrence_exceptions_dst_and_archive(self):
  data=event('series','RRULE:FREQ=WEEKLY;COUNT=3\r\nEXDATE;TZID=America/Los_Angeles:20261108T190000\r\n',start='20261101T190000',end='20261101T210000')+event('old',start='20250101T190000',end='20250101T210000')
  items=parse_feed(feed(data),NOW);self.assertEqual(len(items),3)
  self.assertEqual([x['start'].day for x in items if x['uid']=='series'],[1,15])
  page=render_page(items,'public@example.com',NOW)
  self.assertIn('Past events',page);self.assertIn('2025',page);self.assertIn('Subscribe',page)
 def test_safe_html_and_links(self):
  items=parse_feed(feed(event(extra='DESCRIPTION:<script>alert(1)</script>\\nhttps://example.com/ticket\r\nURL:javascript:alert(1)\r\n')),NOW)
  page=render_page(items,'public@example.com',NOW)
  self.assertNotIn('<script>',page);self.assertNotIn('href="javascript:',page);self.assertIn('https://example.com/ticket',page)
 def test_suspicious_feed_requires_matching_second_fetch(self):
  calls=[]
  def read(url):calls.append(url);return feed('')
  self.assertEqual(fetch_verified('https://calendar.google.com/calendar/ical/x/public/basic.ics',20,NOW,read),[])
  self.assertEqual(len(calls),2)
  seq=iter([feed(''),feed(event())])
  with self.assertRaises(ValueError):fetch_verified('https://calendar.google.com/calendar/ical/x/public/basic.ics',20,NOW,lambda _:next(seq))
 def test_backfill_covers_every_original_block_and_normalizes_nightly_shows(self):
  source=Path(__file__).parent/'fixtures/events-before-public-calendar.html'
  m=build_manifest(source.read_text());self.assertEqual(len(m['sourceListings']),39);self.assertEqual(len(m['events']),40)
  ids=[e['id'] for e in m['events']];self.assertEqual(len(ids),len(set(ids)))
  for event_id in ids:self.assertRegex(event_id,r'^[0-9a-v]{5,1024}$')
  self.assertEqual(sum(x['action']=='duplicate' for x in m['sourceListings']),1)
  shows=[e for e in m['events'] if 'Full Body Sensory' in e['summary']];self.assertEqual(len(shows),3)
  self.assertTrue(any('POSTPONED' in e['summary'] for e in m['events']))
  self.assertEqual(build_manifest(source.read_text()),m)

class EventCalendarLinksTests(unittest.TestCase):
 def test_timed_download_and_google_link_preserve_actual_instants_and_public_fields(self):
  from calendar_feed import event_ics, google_event_url
  from icalendar import Calendar
  from urllib.parse import urlsplit,parse_qs
  e=parse_feed(feed(event(extra='DESCRIPTION:Bring friends\\nhttps://example.com/tickets\r\nLOCATION:Chapel & Garden\r\n')),NOW)[0]
  exported=Calendar.from_ical(event_ics(e,NOW)).walk('VEVENT')
  self.assertEqual(len(exported),1)
  self.assertEqual(exported[0].decoded('DTSTART'),e['start'])
  self.assertEqual(exported[0].decoded('DTEND'),e['end'])
  self.assertEqual(str(exported[0]['LOCATION']),'Chapel & Garden')
  self.assertNotIn('ATTENDEE',exported[0])
  q=parse_qs(urlsplit(google_event_url(e)).query)
  self.assertEqual(q['dates'],['20261102T030000Z/20261102T050000Z'])
  self.assertEqual(q['text'],['Public Concert'])
 def test_all_day_download_keeps_exclusive_end_and_occurrences_are_individual(self):
  from calendar_feed import event_ics, calendar_filename, google_event_url
  from icalendar import Calendar
  from datetime import date
  data=event('series','RRULE:FREQ=WEEKLY;COUNT=2\r\n')
  items=parse_feed(feed(data),NOW)
  self.assertNotEqual(calendar_filename(items[0]),calendar_filename(items[1]))
  self.assertNotIn('RRULE',Calendar.from_ical(event_ics(items[0],NOW)).walk('VEVENT')[0])
  all_day='BEGIN:VEVENT\r\nUID:day\r\nDTSTART;VALUE=DATE:20261101\r\nDTEND;VALUE=DATE:20261103\r\nSUMMARY:Open house\r\nEND:VEVENT\r\n'
  e=parse_feed(feed(all_day),NOW)[0]
  v=Calendar.from_ical(event_ics(e,NOW)).walk('VEVENT')[0]
  self.assertEqual(v.decoded('DTSTART'),date(2026,11,1))
  self.assertEqual(v.decoded('DTEND'),date(2026,11,3))
  self.assertIn('20261101%2F20261103',google_event_url(e))
 def test_every_card_has_a_download_and_generated_file(self):
  from calendar_feed import write_calendar_files, calendar_filename
  from tempfile import TemporaryDirectory
  events=parse_feed(feed(event()),NOW)
  with TemporaryDirectory() as tmp:
   write_calendar_files(events,Path(tmp),NOW)
   self.assertTrue((Path(tmp)/calendar_filename(events[0])).is_file())
   write_calendar_files([],Path(tmp),NOW)
   self.assertFalse((Path(tmp)/calendar_filename(events[0])).exists())
  page=render_page(events,'public@example.com',NOW)
  self.assertIn('Add to calendar',page)
  self.assertIn('Google Calendar',page)
  self.assertIn('download=',page)
  self.assertIn('calendar/'+calendar_filename(events[0]),page)


class EventImageTests(unittest.TestCase):
 def test_verified_image_is_rendered_and_survives_calendar_refresh(self):
  # A UID match survives title/link changes; unrelated events cannot inherit artwork.
  from html.parser import HTMLParser
  class Images(HTMLParser):
   def __init__(self):super().__init__();self.images=[]
   def handle_starttag(self,tag,attrs):
    if tag=='img':self.images.append(dict(attrs))
  events=parse_feed(feed(event('pictured')+event('unpictured')),NOW)
  images={'pictured':{'src':'assets/event-images/concert.webp','alt':'Concert artwork & performers','width':960,'height':480}}
  page=render_page(events,'public@example.com',NOW,images=images)
  parser=Images();parser.feed(page)
  self.assertEqual(len(parser.images),1)
  self.assertEqual(parser.images[0]['src'],'assets/event-images/concert.webp')
  self.assertEqual(parser.images[0]['alt'],'Concert artwork & performers')
  self.assertEqual(parser.images[0]['loading'],'lazy')
  self.assertEqual(parser.images[0]['width'],'960')
  events[0]['title']='Updated concert title'
  self.assertIn('assets/event-images/concert.webp',render_page(events,'public@example.com',NOW,images=images))
  self.assertEqual(page.count('<article class="event-card">'),2)

 def test_missing_or_unsafe_image_keeps_event_details_without_a_broken_image(self):
  events=parse_feed(feed(event()),NOW)
  for image in [None,{}, {'src':'javascript:alert(1)'}, {'src':'../secrets.png'}, {'src':'https://example.com/tracker.png'}]:
   page=render_page(events,'public@example.com',NOW,images={'a':image})
   self.assertNotIn('<img ',page)
   self.assertIn('Public Concert',page)
   self.assertIn('Add to calendar',page)

if __name__=='__main__':unittest.main()
