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
if __name__=='__main__':unittest.main()
