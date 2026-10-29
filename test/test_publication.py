import importlib.util,pathlib,unittest
spec=importlib.util.spec_from_file_location('events',pathlib.Path(__file__).parents[1]/'scripts'/'remove_cancelled_events.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
PAGE='<html><div id="upcoming-events"><p>Check back for upcoming events.</p></div><div id="previous-events"><div class="event_deets"><h3>History</h3><p>January 19 2025</p><div>Original history</div></div></div><footer>Unchanged footer</footer></html>'
NOW='2026-10-29T19:00:00+00:00'
def record(id='recPublic',**fields):return {'id':id,'fields':{'Event Name':'Public event','Event Start Date':'2026-12-16T02:00:00Z','Event End Date':'2026-12-16T05:00:00Z','Publish on website':True,**fields}}
class PublicationTests(unittest.TestCase):
 def test_default_preserves_archive_and_never_publishes_unchecked_private_or_cancelled(self):
  records=[record('recUnchecked',**{'Publish on website':False}),record('recPrivate',**{'Private?':True}),record('recCancelled',Status='Cancelled')]
  self.assertEqual(mod.sync_events(PAGE,records,NOW),PAGE)
 def test_opted_in_event_is_escaped_and_updates_without_duplicate_or_unrelated_changes(self):
  r=record(**{'Event Name':'Party <script>alert(1)</script>','Event Description':'<img src=x onerror=alert(1)>','Event URL':'javascript:alert(1)'})
  out=mod.sync_events(PAGE,[r],NOW)
  self.assertIn('data-airtable-id="recPublic"',out);self.assertIn('Party &lt;script&gt;',out);self.assertNotIn('<script>',out);self.assertNotIn('javascript:',out)
  self.assertIn('Original history',out);self.assertIn('<footer>Unchanged footer</footer>',out);self.assertNotIn('Check back',out)
  r['fields']['Event Name']='Renamed';r['fields']['Event Start Date']='2026-09-16T02:00:00Z';r['fields']['Event End Date']='2026-09-16T05:00:00Z'
  updated=mod.sync_events(out,[r],NOW)
  self.assertEqual(updated.count('data-airtable-id="recPublic"'),1);self.assertNotIn('Party &lt;',updated)
  self.assertGreater(updated.index('Renamed'),updated.index('id="previous-events"'))
  self.assertEqual(mod.sync_events(updated,[r],NOW),updated)
 def test_unchecking_or_private_removes_only_managed_event_missing_record_fails(self):
  r=record();out=mod.sync_events(PAGE,[r],NOW)
  with self.assertRaisesRegex(ValueError,'missing'):mod.sync_events(out,[],NOW)
  for change in [{'Publish on website':False},{'Private?':True},{'Status':'Cancelled'}]:
   r=record(**change);updated=mod.sync_events(out,[r],NOW)
   self.assertNotIn('data-airtable-id="recPublic"',updated);self.assertIn('Original history',updated)
 def test_existing_listing_is_adopted_only_with_unique_identity(self):
  r=record(**{'Event Name':'History','Event Start Date':'2025-01-19T19:00:00Z','Event End Date':'2025-01-19T21:00:00Z'})
  out=mod.sync_events(PAGE,[r],NOW);self.assertEqual(out.count('<h3>History</h3>'),1)
  with self.assertRaisesRegex(ValueError,'Ambiguous'):mod.sync_events(PAGE,[r,{**r,'id':'recOther'}],NOW)
 def test_invalid_opted_in_dates_or_structure_abort(self):
  for fields in [{'Event Start Date':'2026-12-15'},{'Event End Date':'bad'},{'Event End Date':'2026-12-15T00:00:00Z'}]:
   with self.assertRaises(ValueError):mod.sync_events(PAGE,[record(**fields)],NOW)
  with self.assertRaises(ValueError):mod.sync_events(PAGE.replace('id="upcoming-events"','id="wrong"'),[record()],NOW)
