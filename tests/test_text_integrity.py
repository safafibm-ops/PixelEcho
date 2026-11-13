from io import BytesIO
import unittest
from unittest.mock import AsyncMock, patch
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
import server
from text_integrity import compare_text,upload_assessment,paragraphs


def png(value=255):
 im=np.full((400,600,3),value,np.uint8);out=BytesIO();Image.fromarray(im).save(out,'PNG');return out.getvalue()
def para(text,confidence=.99):
 return {'text':text,'confidence':confidence,'polygon':[[.1,.3],[.4,.3],[.4,.38],[.1,.38]]}
ALIGN={'matrix':np.eye(3).tolist(),'query_size':[600,400],'reference_size':[600,400]}

class TextComparisonTests(unittest.TestCase):
 def test_same_text_case_and_punctuation_agree(self):
  result=compare_text(png(),png(),ALIGN,[para('Panel seeks urgent steps for weavers uplift.')],[para('PANEL seeks urgent steps for weavers uplift')])
  self.assertEqual(result['status'],'consistent_in_checked_regions')
  self.assertFalse(result['preview'])
 def test_changed_headline_with_pixel_change_is_flagged(self):
  result=compare_text(png(230),png(255),ALIGN,[para('Authorities seek immediate action on weavers uplift')],[para('Panel seeks urgent steps for weavers uplift')])
  self.assertEqual(result['status'],'differences_found')
  self.assertIn('Authorities',result['regions'][0]['query_text'])
  self.assertTrue(result['preview'].startswith('data:image/jpeg;base64,'))
  score=upload_assessment([{'comparison':result}]);self.assertLessEqual(score['score'],35)
  self.assertIn('Review required',score['verdict'])
 def test_ocr_disagreement_without_pixel_change_is_inconclusive(self):
  result=compare_text(png(),png(),ALIGN,[para('Authorities seek immediate action on weavers uplift')],[para('Panel seeks urgent steps for weavers uplift')])
  self.assertEqual(result['status'],'inconclusive')
 def test_low_confidence_or_unaligned_never_yields_trust(self):
  result=compare_text(png(),png(),ALIGN,[para('Some long headline text here',.4)],[para('Some long headline text here')])
  self.assertEqual(result['status'],'inconclusive');self.assertIsNone(upload_assessment([{'comparison':result}])['score'])
  self.assertEqual(compare_text(png(),png(),None,[],[])['status'],'inconclusive')
 def test_no_references_unknown_and_duplicates_do_not_inflate(self):
  self.assertIsNone(upload_assessment([])['score'])
  item={'comparison':{'status':'consistent_in_checked_regions','regions':[{'status':'agreement'}]}}
  self.assertEqual(upload_assessment([item])['score'],upload_assessment([item,item])['score'])
 def test_missing_ocr_confidence_not_invented(self):
  self.assertEqual(paragraphs({'textAnnotations':[{'description':'text'}]}),[])

class IntegrityEndpointTests(unittest.TestCase):
 def setUp(self):server.cases.clear();self.client=TestClient(server.app)
 def tearDown(self):server.cases.clear()
 def test_unknown_case_and_origin_denied(self):
  self.assertEqual(self.client.post('/api/text-integrity',json={'case_id':'missing'}).status_code,404)
  self.assertEqual(self.client.post('/api/text-integrity',json={'case_id':'missing'},headers={'Origin':'https://foreign.example'}).status_code,403)
 def test_no_candidates_no_network_and_cached_export(self):
  import time
  server.cases['test']={'created':time.monotonic(),'search':{'pages':[]},'verification':[],'report':{},'query_bytes':png()}
  with patch('server.read_key',return_value='secret'),patch('server.document_ocr',new_callable=AsyncMock) as ocr:
   first=self.client.post('/api/text-integrity',json={'case_id':'test'});second=self.client.post('/api/text-integrity',json={'case_id':'test'})
  self.assertEqual(first.status_code,200);self.assertIsNone(first.json()['upload_assessment']['score']);ocr.assert_not_called()
  self.assertEqual(first.json(),second.json())
  export=self.client.get('/api/reports/test');self.assertNotIn('query_bytes',export.text);self.assertNotIn('secret',export.text)

 def test_real_candidate_fetch_alignment_ocr_and_caching(self):
  import time
  import cv2
  from test_remaining_stages import pattern
  base=pattern()
  raw=cv2.imencode('.png',base)[1].tobytes()
  image_url='https://example.com/photo.png'
  server.cases['test']={'created':time.monotonic(),'query_bytes':raw,'search':{'pages':[{'url':'https://example.com/article','full_matches':[{'url':image_url}],'partial_matches':[]}]},'verification':[],'report':{}}
  with patch('server.read_key',return_value='secret'),patch('server.SafeFetcher.fetch',new_callable=AsyncMock,return_value=(200,image_url,raw)) as fetch,patch('server.document_ocr',new_callable=AsyncMock,return_value=[para('Panel seeks urgent steps for weavers uplift')]) as ocr:
   response=self.client.post('/api/text-integrity',json={'case_id':'test','url':'https://private.invalid/'})
   self.assertEqual(response.status_code,200)
   self.assertEqual(response.json()['checks'][0]['comparison']['status'],'consistent_in_checked_regions')
   self.client.post('/api/text-integrity',json={'case_id':'test'})
   self.assertEqual(ocr.call_count,2);fetch.assert_awaited_once_with(image_url,image=True)
 def test_unavailable_reference_produces_unknown(self):
  import time
  server.cases['test']={'created':time.monotonic(),'query_bytes':png(),'search':{'pages':[],'full_matches':[{'url':'https://example.com/img'}]},'verification':[],'report':{}}
  with patch('server.read_key',return_value='secret'),patch('server.SafeFetcher.fetch',new_callable=AsyncMock,side_effect=ValueError('secret error')):
   response=self.client.post('/api/text-integrity',json={'case_id':'test'})
  self.assertIsNone(response.json()['upload_assessment']['score']);self.assertNotIn('secret',response.text)

 def test_similar_image_is_compared_even_after_many_exact_candidates(self):
  import time
  server.cases['test']={'created':time.monotonic(),'query_bytes':png(),'search':{'pages':[],'full_matches':[{'url':f'https://example.com/{i}'} for i in range(5)],'similar_images':[{'url':'https://example.com/similar'}]},'verification':[],'report':{}}
  with patch('server.read_key',return_value='secret'),patch('server.SafeFetcher.fetch',new_callable=AsyncMock,side_effect=ValueError('unavailable')) as fetch:
   result=self.client.post('/api/text-integrity',json={'case_id':'test'})
  self.assertEqual(result.status_code,200)
  self.assertIn('https://example.com/similar',[c.args[0] for c in fetch.call_args_list]);self.assertEqual(fetch.call_count,4)
