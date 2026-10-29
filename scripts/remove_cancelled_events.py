"""Remove verified cancelled events from the existing public list; never publish inquiries."""
from html.parser import HTMLParser
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import json, os, re, urllib.parse, urllib.request

def normalize(text): return ' '.join(text.casefold().split())
def cancelled(fields):
    return any(normalize(str(fields.get(k,''))) in ('cancelled','canceled') for k in ('Status','status')) or '[CHAPEL CANCELLATION ' in fields.get('Concierge Log','')

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

def read_records(token):
    result=[];seen=set();offset=None
    while True:
        params=[('pageSize','100')]+[('fields[]',f) for f in ['Event Name','Event Start Date','Status','Concierge Log']]
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
    page=Path('events.html'); records=read_records(os.environ['AIRTABLE_API_KEY'])
    text,removed=remove_cancelled(page.read_text(),records)
    if removed:
        tmp=page.with_suffix('.tmp');tmp.write_text(text);tmp.replace(page)
    print(json.dumps({'removed_count':len(removed)}))
