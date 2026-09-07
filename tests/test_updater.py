import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import tempfile
import json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from search import identity, parse, search, SHARE
from verify import approved
from update_listings import merge, update

URL='https://www.kleinanzeigen.de/s-anzeige/yamaha-xt-600z-tenere-3aj-restauriert/3483708231-305-8487'

class UpdaterTests(unittest.TestCase):
 def test_search_current_markup_and_pagination(self):
  html=('<main id="srchrslt-adtable"><h3><a href="'+URL.replace('https://www.kleinanzeigen.de','')+'">Yamaha XT600</a></h3></main><a href="/s-motorraeder-roller/seite:2/xt600/k0c305">Next</a>').encode()
  errors=[]
  with patch('search.fetch',return_value=(200,'search',html)):
   urls=search({'queries':['xt600'],'max_pages_per_query':1,'request_delay_seconds':0,'seed_urls':[]},errors)
  self.assertIn(URL,urls)
  self.assertEqual(len(errors),1)
 def test_exact_url(self):
  self.assertEqual(identity(URL+SHARE),('3483708231',URL))
  for bad in ['https://evil.com'+URL.split('.de')[1],URL.replace('-305-','-306-')]:
   with self.assertRaises(ValueError):identity(bad)
 def test_redirect_removed(self):
  self.assertFalse(parse(URL,200,'https://www.kleinanzeigen.de/s-motorraeder-roller/k0c305',b'')['active'])
 def test_challenge_not_removed(self):
  with self.assertRaises(ValueError):parse(URL,200,URL,b'<h1>Captcha</h1>')
 def test_title_never_verifies(self):
  self.assertFalse(approved({'id':'3483708231','title':'3AJ red white'}, {}, 'hash'))
 def test_changed_image_revokes_review(self):
  row={'id':'1','image_url':'photo','listing_url':URL}
  review={'1':dict(rule_version=1,image_sha256='old',image_url='photo',listing_url=URL,decision='approved',red_white=True,whole_motorcycle=True,visually_verified_3aj=True,evidence='observed',reviewed_at='today')}
  self.assertTrue(approved(row,review,'old'))
  self.assertFalse(approved(row,review,'new'))
 def test_price_history_survives(self):
  old={'first_seen':'start','price_eur':6999}
  one=merge(old,{'active':True,'price_eur':6499},'next')
  two=merge(one,{'active':True,'price_eur':6499},'later')
  self.assertEqual(two['previous_price_eur'],6999)
  self.assertEqual(two['first_seen'],'start')
 def test_network_failure_preserves_history(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'data').mkdir();(root/'config').mkdir()
   old={'id':'3483708231','listing_url':URL,'active':True,'visually_verified_3aj':True,'price_eur':6999,'first_seen':'start','last_seen':'previous'}
   (root/'data/listings.json').write_text(json.dumps({'last_updated':'previous','listings':[old]}))
   (root/'data/visual_reviews.json').write_text('{}')
   (root/'config/search.json').write_text(json.dumps({'seed_urls':[URL],'request_delay_seconds':0}))
   with patch('update_listings.ROOT',root),patch('update_listings.fetch',side_effect=TimeoutError('network')):
    update(True)
   result=json.loads((root/'data/listings.json').read_text())
   self.assertEqual(result['last_updated'],'previous')
   self.assertEqual(result['listings'][0]['price_eur'],6999)
   self.assertTrue(result['listings'][0]['active'])
   self.assertEqual(result['listings'][0]['check_status'],'error')
 def test_known_search_result_reuses_cached_details(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'data').mkdir();(root/'config').mkdir()
   old={'id':'3483708231','listing_url':URL,'active':True,'visually_verified_3aj':True,'price_eur':6999,'first_seen':'start','last_seen':'previous'}
   (root/'data/listings.json').write_text(json.dumps({'last_updated':'previous','listings':[old]}))
   (root/'data/visual_reviews.json').write_text('{}')
   (root/'config/search.json').write_text(json.dumps({'seed_urls':[],'request_delay_seconds':0}))
   with patch('update_listings.ROOT',root),patch('update_listings.search',return_value={URL}),patch('update_listings.fetch') as fetch_mock:
    update(False)
   fetch_mock.assert_not_called()
   result=json.loads((root/'data/listings.json').read_text())
   self.assertEqual(result['listings'][0]['check_status'],'cached')
if __name__=='__main__':unittest.main()
