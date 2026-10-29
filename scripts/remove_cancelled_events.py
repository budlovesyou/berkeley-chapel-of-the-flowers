"""Remove verified cancelled events from the existing public list; never publish inquiries."""
from html.parser import HTMLParser
from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import json, os, re, urllib.parse, urllib.request

def normalize(text): return ' '.join(text.casefold().split())
def cancelled(fields):
    return any(normalize(str(fields.get(k,''))) in ('cancelled','canceled') for k in ('Status','status'))

class EventBlocks(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True); self.text=text; self.lines=text.splitlines(keepends=True);self.offsets=[0]
        for line in self.lines:self.offsets.append(self.offsets[-1]+len(line))
        self.depth=0;self.active=None;self.capture=None;self.blocks=[];self.feed(text);self.close()
        if self.active:raise ValueError('Unclosed public event block')
    def position(self):
        line,col=self.getpos();return self.offsets[line-1]+col
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='div':
            self.depth+=1
            if 'event_deets' in attrs.get('class','').split():
                if self.active:raise ValueError('Nested public event blocks')
                self.active={'start':self.position(),'depth':self.depth,'title':'','date':'','id':attrs.get('data-airtable-id')}
        if self.active and (tag=='h3' or (tag=='p' and not self.active['date'])):self.capture='title' if tag=='h3' else 'date'
    def handle_data(self,data):
        if self.active and self.capture:self.active[self.capture]+=data
    def handle_endtag(self,tag):
        if tag in ('h3','p'):self.capture=None
        if tag=='div':
            if self.active and self.active['depth']==self.depth:
                self.active['end']=self.position()+len('</div>');self.blocks.append(self.active);self.active=None;self.capture=None
            self.depth-=1

def remove_cancelled(page,records):
    cuts=[];removed=[]
    for block in EventBlocks(page).blocks:
        if block['id']: matches=[r for r in records if r['id']==block['id']]
        else:
            day=re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})',block['date'],re.I)
            if not day:continue
            displayed=datetime.strptime(' '.join(day.groups()),'%B %d %Y').date()
            matches=[]
            for r in records:
                f=r.get('fields',{})
                if normalize(f.get('Event Name',''))!=normalize(block['title']):continue
                try: actual=datetime.fromisoformat(f['Event Start Date'].replace('Z','+00:00')).astimezone(ZoneInfo('America/Los_Angeles')).date()
                except (KeyError,ValueError):continue
                if actual==displayed:matches.append(r)
        if not any(cancelled(r.get('fields',{})) for r in matches):continue
        if len(matches)!=1:raise ValueError('Ambiguous cancellation match; public listing retained for manual review')
        cuts.append((block['start'],block['end']));removed.append(matches[0]['id'])
    for start,end in reversed(cuts):page=page[:start]+page[end:]
    return page,removed

class Sections(EventBlocks):
    def __init__(self,text):
        self.sections={};self.open_sections={};super().__init__(text)
        if self.open_sections:raise ValueError('Unclosed publication section')
    def handle_starttag(self,tag,attrs):
        super().handle_starttag(tag,attrs)
        name=dict(attrs).get('id')
        if tag=='div' and name in ('upcoming-events','previous-events'):
            if name in self.sections or name in self.open_sections:raise ValueError('Duplicate publication section')
            self.open_sections[name]=(self.depth,self.position()+len(self.get_starttag_text()))
    def handle_endtag(self,tag):
        if tag=='div':
            for name,(depth,start) in list(self.open_sections.items()):
                if depth==self.depth:self.sections[name]=(start,self.position());del self.open_sections[name]
        super().handle_endtag(tag)

def timed(value):
    try:
        result=datetime.fromisoformat(value.replace('Z','+00:00'))
        if result.tzinfo is None:raise ValueError('Timezone required')
        return result.astimezone(ZoneInfo('America/Los_Angeles'))
    except (AttributeError,TypeError,ValueError) as error:raise ValueError('Invalid publication date') from error

def block_day(block):
    day=re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})',block['date'],re.I)
    return datetime.strptime(' '.join(day.groups()),'%B %d %Y').date() if day else None

def public(fields):
    return fields.get('Publish on website') is True and fields.get('Private?') is not True and not cancelled(fields)

def render_event(record):
    fields=record['fields'];start=timed(fields.get('Event Start Date'));end=timed(fields.get('Event End Date'))
    title=fields.get('Event Name')
    if not isinstance(title,str) or not title.strip() or end<=start:raise ValueError('Incomplete public event')
    if not re.fullmatch(r'rec[A-Za-z0-9]+',record['id']):raise ValueError('Invalid record identity')
    fmt=lambda d:d.strftime('%A %B %d %Y %I:%M %p')
    parts=[f'<div class="event_deets" data-airtable-id="{record["id"]}">',f'<h3>{escape(title)}</h3>',f'<p>{fmt(start)} until {fmt(end)}</p>']
    description=fields.get('Event Description','')
    if description:
        parts+=['<button class="toggle-btn" onclick="toggleDescription(this)">Show Details</button>', '<div class="event_description" style="display: none;"><p>'+escape(str(description)).replace('\n','<br>')+'</p></div>']
    for key,label in [('Event URL','Event link'),('Event Facebook URL','Facebook link')]:
        value=fields.get(key,'')
        if isinstance(value,str):
            parsed=urllib.parse.urlsplit(value)
            if parsed.scheme.lower() in ('http','https') and parsed.netloc:parts.append(f'<a href="{escape(value,quote=True)}">{label}</a>')
    parts.append('</div>');return '\n'.join(parts),end

def sync_events(page,records,now=None):
    now=timed(now) if now else datetime.now(ZoneInfo('America/Los_Angeles'))
    by_id={r['id']:r for r in records}
    if len(by_id)!=len(records):raise ValueError('Duplicate source record')
    page,_=remove_cancelled(page,records)
    blocks=EventBlocks(page).blocks;cuts={};eligible=[r for r in records if public(r.get('fields',{}))]
    managed=[b for b in blocks if b['id']]
    for block in managed:
        if block['id'] not in by_id:raise ValueError('Managed source record is missing; listing retained for review')
        cuts[block['start']]=block['end']
    groups={'upcoming-events':[],'previous-events':[]}
    for record in eligible:
        rendered,end=render_event(record);fields=record['fields'];start=timed(fields['Event Start Date'])
        matches=[b for b in blocks if b['id']==record['id']]
        if not matches:
            matches=[b for b in blocks if not b['id'] and normalize(b['title'])==normalize(fields['Event Name']) and block_day(b)==start.date()]
            if matches:
                peers=[]
                for other in records:
                    f=other.get('fields',{})
                    if normalize(f.get('Event Name',''))!=normalize(fields['Event Name']):continue
                    try:day=timed(f.get('Event Start Date')).date()
                    except ValueError:continue
                    if day==start.date():peers.append(other)
                if len(peers)!=1:raise ValueError('Ambiguous source identity; listing retained for review')
        if len(matches)>1:raise ValueError('Ambiguous public listing; retained for review')
        for block in matches:cuts[block['start']]=block['end']
        groups['previous-events' if end<=now else 'upcoming-events'].append((start,record['id'],rendered))
    if not cuts and not eligible:return page
    for start,end in sorted(cuts.items(),reverse=True):page=page[:start]+page[end:]
    sections=Sections(page).sections
    if set(sections)!=set(groups):raise ValueError('Missing publication sections')
    for name,(start,end) in sorted(sections.items(),key=lambda pair:pair[1][0],reverse=True):
        content=page[start:end]
        if groups[name]:content=content.replace('<p>Check back for upcoming events.</p>','')
        content+=''.join(item[2] for item in sorted(groups[name]))
        page=page[:start]+content+page[end:]
    return page

def read_records(token):
    result=[];seen=set();offset=None
    while True:
        params=[('pageSize','100')]+[('fields[]',f) for f in ['Event Name','Event Start Date','Event End Date','Status','Private?','Publish on website','Event Description','Event URL','Event Facebook URL']]
        if offset:params.append(('offset',offset))
        url='https://api.airtable.com/v0/appT25NC13v3OxP1O/tbl0vgcerZ6Fl53Jf?'+urllib.parse.urlencode(params)
        request=urllib.request.Request(url,headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(request,timeout=30) as response:data=json.load(response)
        if not isinstance(data.get('records'),list):raise ValueError('Invalid Airtable response')
        result.extend(data['records']);offset=data.get('offset')
        if not offset:return result
        if offset in seen or len(seen)>=100:raise ValueError('Incomplete Airtable pagination')
        seen.add(offset)

if __name__=='__main__':
    page=Path('events.html');records=read_records(os.environ['AIRTABLE_API_KEY'])
    before=page.read_text();text=sync_events(before,records)
    if text!=before:
        tmp=page.with_suffix('.tmp');tmp.write_text(text);tmp.replace(page)
    print(json.dumps({'changed':text!=before,'public_opt_ins':sum(public(r.get('fields',{})) for r in records)}))
