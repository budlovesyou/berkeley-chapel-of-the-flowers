"""Generate the public events page exclusively from the public Google ICS feed."""
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, quote, urlencode
from urllib.request import Request, urlopen
import argparse, hashlib, json, re
from icalendar import Calendar, Event
import recurring_ical_events
from remove_cancelled_events import EventBlocks

ZONE = ZoneInfo('America/Los_Angeles')
VENUE = 'Chapel of the Flowers, 3049 Adeline Street, Berkeley, CA 94703'
ROOT = Path(__file__).resolve().parents[1]

class Text(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True); self.parts=[]; self.links=[]; self.feed(html)
    def handle_data(self, value): self.parts.append(value)
    def handle_starttag(self, tag, attrs):
        if tag in ('p','br','li'): self.parts.append('\n')
        if tag=='a':
            url=dict(attrs).get('href','')
            if safe_url(url): self.links.append(url)
    def handle_endtag(self,tag):
        if tag in ('p','li'): self.parts.append('\n')
    def text(self): return re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+','\n\n',''.join(self.parts)).strip()

def safe_url(value):
    try:
        p=urlsplit(value)
        return p.scheme.lower() in ('http','https') and bool(p.netloc) and not p.username and not p.password
    except ValueError: return False

def aware(value):
    if isinstance(value,datetime):
        if value.tzinfo is None: raise ValueError('Calendar datetime needs a timezone')
        return value.astimezone(ZONE)
    if isinstance(value,date): return datetime.combine(value,time.min,ZONE)
    raise ValueError('Invalid event boundary')

def parse_feed(data, now=None):
    now=now or datetime.now(ZONE)
    if not data.strip().startswith(b'BEGIN:VCALENDAR') or not data.strip().endswith(b'END:VCALENDAR'): raise ValueError('Incomplete ICS calendar')
    calendar=Calendar.from_ical(data)
    if calendar.errors: raise ValueError('Malformed ICS calendar')
    components=calendar.walk('VEVENT')
    for component in components:
        if component.errors or not component.get('UID'): raise ValueError('Malformed calendar event')
    starts=[aware(e.decoded('DTSTART')) for e in components if e.get('DTSTART')]
    earliest=min(starts,default=now)
    try: until=now.replace(year=now.year+1)
    except ValueError: until=now.replace(year=now.year+1,day=28)
    occurrences=recurring_ical_events.of(calendar).between(earliest,until)
    result=[]; seen=set()
    for item in occurrences:
        if str(item.get('CLASS','PUBLIC')).upper() in ('PRIVATE','CONFIDENTIAL') or str(item.get('STATUS','')).upper()=='CANCELLED': continue
        raw_title=item.get('SUMMARY','')
        if isinstance(raw_title,list): raise ValueError('Repeated event title')
        title=str(raw_title).strip()
        if not title or title.casefold() in ('busy','private event','reserved'): continue
        start=aware(item.decoded('DTSTART')); end=aware(item.decoded('DTEND'))
        if end<=start: raise ValueError('Nonpositive event duration')
        uid=str(item['UID']); key=(uid,start.isoformat())
        if key in seen: raise ValueError('Duplicate public calendar occurrence')
        seen.add(key)
        description=str(item.get('DESCRIPTION',''))
        urls=[str(item.get('URL',''))]+Text(description).links+re.findall(r'https?://[^\s<>"\)]+',description)
        links=list(dict.fromkeys(u for u in urls if safe_url(u)))
        result.append(dict(uid=uid,title=title,start=start,end=end,allDay=not isinstance(item.decoded('DTSTART'),datetime),description=Text(description).text() if '<' in description else description,links=links,location=str(item.get('LOCATION',VENUE))))
    return sorted(result,key=lambda e:(e['start'],e['uid']))

def read_url(url):
    request=Request(url,headers={'User-Agent':'ChapelPublicEvents/1.0','Cache-Control':'no-cache'})
    with urlopen(request,timeout=30) as response:
        data=response.read(10_000_001)
        if len(data)>10_000_000: raise ValueError('Public calendar response exceeds limit')
        return data

def fetch_verified(url, previous_count, now=None, reader=read_url):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname!='calendar.google.com' or not parsed.path.endswith('/public/basic.ics'): raise ValueError('Only the anonymous public Google ICS feed is allowed')
    first=reader(url); events=parse_feed(first,now)
    if previous_count and len(events)<previous_count/2:
        second=reader(url); again=parse_feed(second,now)
        signature=lambda es:[(e['uid'],e['start'].isoformat(),e['end'].isoformat()) for e in es]
        if signature(events)!=signature(again): raise ValueError('Unexpected calendar disappearance is not confirmed; previous page retained')
    return events

def calendar_filename(e):
    key=json.dumps([e['uid'],e['start'].isoformat()])
    return hashlib.sha256(key.encode()).hexdigest()[:32]+'.ics'

def event_description(e):
    return '\n\n'.join([e['description']]+[u for u in e['links'] if u not in e['description']]).strip()

def google_event_url(e):
    def stamp(d):
        return d.strftime('%Y%m%d') if e['allDay'] else d.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    # Keep template URLs usable even when historical descriptions are very long.
    details=event_description(e)
    if len(details)>1200: details=details[:1200]+'…\nFull event details: https://chapeloftheflowers.love/events.html'
    return 'https://calendar.google.com/calendar/render?'+urlencode({'action':'TEMPLATE','text':e['title'],'dates':stamp(e['start'])+'/'+stamp(e['end']),'ctz':str(ZONE),'location':e['location'],'details':details})

def event_ics(e,now=None):
    calendar=Calendar();calendar.add('prodid','-//Chapel of the Flowers//Public Events//EN');calendar.add('version','2.0')
    item=Event()
    item.add('uid',calendar_filename(e)[:-4]+'@chapeloftheflowers.love')
    item.add('dtstamp',now or datetime.now(timezone.utc))
    for prop,key in [('dtstart','start'),('dtend','end')]:
        item.add(prop,e[key].date() if e['allDay'] else e[key].astimezone(timezone.utc))
    item.add('summary',e['title']);item.add('description',event_description(e));item.add('location',e['location']);item.add('class','PUBLIC')
    if e['links']:item.add('url',e['links'][0])
    # Export just the occurrence whose card was selected, never the full series.
    calendar.add_component(item)
    return calendar.to_ical()

def write_calendar_files(events,directory,now=None):
    files=[(calendar_filename(e),event_ics(e,now)) for e in events]
    directory.mkdir(parents=True,exist_ok=True)
    for name,data in files:
        target=directory/name;temporary=target.with_suffix('.ics.tmp')
        temporary.write_bytes(data);temporary.replace(target)
    current={name for name,_ in files}
    for old in directory.glob('*.ics'):
        if re.fullmatch(r'[0-9a-f]{32}\.ics',old.name) and old.name not in current: old.unlink()

def card(e):
    start,end=e['start'],e['end']
    day=start.strftime('%A, %B %-d, %Y')
    if e['allDay']:
        last=(end-timedelta(days=1)).date(); hours='All day'+(f' · through {last:%B %d, %Y}' if last!=start.date() else '')
    else:
        hours=f'{start:%-I:%M %p} – '+(f'{end:%B %-d, %Y}, ' if end.date()!=start.date() else '')+f'{end:%-I:%M %p}'
    description=f'<details class="event-details"><summary>Event details</summary><div class="description">{escape(e["description"])}</div></details>' if e['description'] else ''
    links=''.join(f'<a class="event-link" href="{escape(u,quote=True)}" rel="noopener noreferrer">{"Tickets &amp; information" if i==0 else "More information"} <span aria-hidden="true">↗</span></a>' for i,u in enumerate(e['links']))
    calendar_links=f'<details class="add-calendar"><summary>Add to calendar</summary><div><a href="{escape(google_event_url(e),quote=True)}" rel="noopener noreferrer">Google Calendar</a><a href="calendar/{calendar_filename(e)}" download="chapel-event.ics">Apple Calendar / Outlook (.ics)</a></div></details>'
    return f'<article class="event-card"><p class="event-date"><time datetime="{start.isoformat()}">{escape(day)}</time></p><h3>{escape(e["title"])}</h3><p class="event-time">{escape(hours)}</p>{description}<div class="event-links">{links}</div>{calendar_links}</article>'

def render_page(events,calendar_id,now=None):
    now=now or datetime.now(ZONE)
    upcoming=[e for e in events if e['end']>now]; past=sorted((e for e in events if e['end']<=now),key=lambda e:e['start'],reverse=True)
    upcoming_html=''.join(card(e) for e in upcoming) or '<div class="empty"><h3>More gatherings to come</h3><p>New public events will appear here once they’re announced. Subscribe to the calendar to stay in the loop.</p></div>'
    years=sorted({e['start'].year for e in past},reverse=True)
    history=''.join(f'<details class="archive-year"><summary>{year} <span>{sum(e["start"].year==year for e in past)} events</span></summary><div class="event-grid">'+''.join(card(e) for e in past if e['start'].year==year)+'</div></details>' for year in years) or '<p>Past public events will appear here.</p>'
    encoded=quote(calendar_id,safe=''); subscribe='https://calendar.google.com/calendar/u/0/r?cid='+encoded
    ics='https://calendar.google.com/calendar/ical/'+encoded+'/public/basic.ics'
    template=(ROOT/'events.template.html').read_text()
    values={'UPCOMING':upcoming_html,'ARCHIVE':history,'SUBSCRIBE':escape(subscribe,quote=True),'ICS':escape(ics,quote=True),'UPDATED':now.strftime('%B %-d, %Y at %-I:%M %p'),'UPDATED_ISO':now.isoformat(),'COUNT':str(len(events))}
    for name,value in values.items(): template=template.replace('{{'+name+'}}',value)
    return '\n'.join(line.rstrip() for line in template.splitlines())+'\n'

def parse_dates(value):
    start_text,end_text=value.strip().split(' until ',1)
    start=datetime.strptime(start_text,'%A %B %d %Y %I:%M %p').replace(tzinfo=ZONE)
    try:end=datetime.strptime(end_text,'%A %B %d %Y %I:%M %p').replace(tzinfo=ZONE)
    except ValueError:end=datetime.combine(start.date(),datetime.strptime(end_text,'%I:%M %p').time(),ZONE)
    if end<=start: raise ValueError('Ambiguous historical date range')
    return start,end

def build_manifest(html):
    events={};listings=[]
    for n,block in enumerate(EventBlocks(html).blocks,1):
        raw=html[block['start']:block['end']];title=block['title'].strip();start,end=parse_dates(block['date'])
        match=re.search(r'<div class="event_description"[^>]*>([\s\S]*?)</div>',raw)
        content=Text(match.group(1) if match else '');links=Text(raw).links
        description=content.text();description+='\n\n'+'\n'.join(u for u in dict.fromkeys(links) if u not in description) if links else ''
        dates=[(start,end)];action='import'
        if 'Full Body Sensory Music Journey' in title and '3 Shows | October 24, 25 and 26 | 7-9 PM' in description:
            dates=[(datetime(2025,10,d,19,tzinfo=ZONE),datetime(2025,10,d,21,tzinfo=ZONE)) for d in (24,25,26)];action='split nightly shows'
        ids=[]
        for a,b in dates:
            identity=json.dumps([title.casefold(),a.isoformat(),b.isoformat()],ensure_ascii=False)
            event_id='chapelhist'+hashlib.sha256(identity.encode()).hexdigest()[:48]
            body={'id':event_id,'summary':title,'start':{'dateTime':a.isoformat(),'timeZone':str(ZONE)},'end':{'dateTime':b.isoformat(),'timeZone':str(ZONE)},'description':description.strip(),'location':VENUE,'visibility':'public','transparency':'transparent','reminders':{'useDefault':False}}
            if event_id in events:
                normalize=lambda t:' '.join(t.split())
                if normalize(events[event_id]['description'])!=normalize(body['description']): raise ValueError('Conflicting duplicate historical listing')
                action='duplicate'
            else:events[event_id]=body
            ids.append(event_id)
        listings.append({'block':n,'title':title,'displayedTime':block['date'],'action':action,'eventIds':ids})
    return {'version':1,'sourceSha256':hashlib.sha256(html.encode()).hexdigest(),'sourceListings':listings,'events':list(events.values()),'notes':['Displayed historical times and original public descriptions preserved, including any differences between them. Postponed titles remain labeled.']}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest-from');parser.add_argument('--output');parser.add_argument('--feed-file');args=parser.parse_args()
    if args.manifest_from:
        manifest=build_manifest(Path(args.manifest_from).read_text());Path(args.output).write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'listings':len(manifest['sourceListings']),'events':len(manifest['events'])}));return
    cfg=json.loads((ROOT/'public-calendar.json').read_text());target=Path(args.output) if args.output else ROOT/'events.html';now=datetime.now(ZONE)
    old=target.read_text() if target.exists() else '';count=re.search(r'data-event-count="(\d+)"',old)
    url='https://calendar.google.com/calendar/ical/'+quote(cfg['calendarId'],safe='')+'/public/basic.ics'
    events=parse_feed(Path(args.feed_file).read_bytes(),now) if args.feed_file else fetch_verified(url,int(count[1]) if count else 0,now)
    page=render_page(events,cfg['calendarId'],now)
    write_calendar_files(events,target.parent/'calendar',now)
    # Atomic replacement happens only after a complete fetch, parse, render and export.
    temporary=target.with_suffix('.html.tmp');temporary.write_text(page);temporary.replace(target)
    print(json.dumps({'events':len(events),'output':str(target)}))
if __name__=='__main__':main()
