import importlib.util, pathlib, unittest
spec=importlib.util.spec_from_file_location('events',pathlib.Path(__file__).parents[1]/'scripts'/'remove_cancelled_events.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class CleanupTests(unittest.TestCase):
 def test_remove_cancelled_preserve_unpublished_and_footer(self):
  page='<html><div id="upcoming-events"><div class="event_deets"><h3>Party &amp; Dance</h3><p>Tuesday December 15 2026 6:00 PM</p><div>Details</div></div><div class="event_deets"><h3>Keep</h3><p>Wednesday December 16 2026 6:00 PM</p></div></div><footer>Keep footer</footer></html>'
  records=[{'id':'recCancelled','fields':{'Event Name':'Party & Dance','Event Start Date':'2026-12-16T02:00:00Z','Concierge Log':'[CHAPEL CANCELLATION event1]'}},{'id':'recPrivate','fields':{'Event Name':'Private wedding','Event Start Date':'2026-12-17T02:00:00Z'}}]
  out,removed=mod.remove_cancelled(page,records)
  self.assertNotIn('Party',out);self.assertIn('Keep footer',out);self.assertIn('<h3>Keep</h3>',out);self.assertNotIn('Private wedding',out);self.assertEqual(removed,['recCancelled'])
 def test_same_name_different_dates_and_ambiguous_same_date(self):
  page='<div class="event_deets"><h3>Party</h3><p>December 15, 2026</p></div>'
  r={'id':'a','fields':{'Event Name':'Party','Event Start Date':'2026-12-16T02:00:00Z','Status':'Cancelled'}}
  other={'id':'b','fields':{'Event Name':'Party','Event Start Date':'2026-12-17T02:00:00Z','Status':'Confirmed'}}
  self.assertEqual(mod.remove_cancelled(page,[r,other])[0],'')
  other['fields']['Event Start Date']=r['fields']['Event Start Date']
  with self.assertRaisesRegex(ValueError,'Ambiguous'):mod.remove_cancelled(page,[r,other])
 def test_closed_alone_is_not_cancellation_and_bad_page_is_not_overwritten(self):
  page='<div class="event_deets"><h3>History</h3><p>December 15 2026</p></div>'
  r={'id':'a','fields':{'Event Name':'History','Event Start Date':'2026-12-16T02:00:00Z','Concierge Stage':'Closed'}}
  self.assertEqual(mod.remove_cancelled(page,[r])[0],page)
  with self.assertRaises(ValueError):mod.remove_cancelled(page[:-6],[r])
if __name__=='__main__':unittest.main()
