import unittest
from io import BytesIO
from PIL import Image
from investigation import observations, crop_photo, rank_pages, retrieve_passages, keyword_search
from unittest.mock import patch

class InvestigationTests(unittest.IsolatedAsyncioTestCase):
 def test_ocr_queries_keep_local_clues_and_coordinates(self):
  result=observations({'textAnnotations':[{'description':"It's Mangalore News\nMangaluru City Corporation orders removal of unauthorised street vendors"},{'description':'MCC','boundingPoly':{'vertices':[{'x':2,'y':4},{'x':30,'y':4},{'x':30,'y':12}]}}]})
  self.assertIn('Mangaluru', ' '.join(result['queries']))
  self.assertEqual(result['words'][0]['vertices'][0],{'x':2,'y':4})
  self.assertLessEqual(len(result['queries']),3)
 def test_generic_buildings_demoted_and_image_leads_retained(self):
  pages=[{'url':'https://example.com/generic','title':'How to design a commercial building','full_matches':[],'partial_matches':[]}, {'url':'https://local.example/news','title':'Mangaluru City Corporation removes street vendors','full_matches':[],'partial_matches':[]}, {'url':'https://photos.example/original','title':'Archive','full_matches':[{'url':'https://photos.example/img.jpg'}],'partial_matches':[]}]
  main,related=rank_pages(pages,{'text':'Mangaluru City Corporation orders removal of unauthorised street vendors'})
  self.assertEqual(len(main),2);self.assertEqual(related[0]['url'],pages[0]['url'])
 def test_crop_only_removes_separated_text_bands(self):
  image=BytesIO();Image.new('RGB',(400,500)).save(image,'JPEG')
  clue={'words':[{'vertices':[{'x':10,'y':410},{'x':350,'y':450}]}]}
  data,box=crop_photo(image.getvalue(),clue)
  self.assertEqual(box,[0,0,400,406]);self.assertEqual(Image.open(BytesIO(data)).size,(400,406))
  self.assertIsNone(crop_photo(image.getvalue(),{'words':[]}))
 async def test_missing_keyword_key_does_not_network(self):
  with patch('investigation.httpx.AsyncClient',side_effect=AssertionError('No request allowed')):
   pages,status=await keyword_search(['Mangaluru MCC'],'')
  self.assertFalse(pages);self.assertEqual(status['status'],'unavailable')
 def test_retrieved_passages_are_cited_not_generated_answers(self):
  result=retrieve_passages({'pages':[{'id':'one','requested_url':'https://example.com','status':'collected','text':'Mangaluru Corporation issued a street vendors notice.'}]},{'text':'Mangaluru City Corporation street vendors'})
  self.assertEqual(result['passages'][0]['evidence_id'],'one')
  self.assertEqual(result['multimodal_answer_status'],'not_configured')
