import unittest
from source_ranking import rank_sources

class SourceRankingTests(unittest.TestCase):
 def pages(self):return [{'url':'https://example.org/new','title':'New'},{'url':'https://example.com/old','title':'Old'},{'url':'https://unknown.test/page','title':'Unknown'}]
 def evidence(self):return {'pages':[{'requested_url':'https://example.org/new','id':'new','status':'collected','page_dates':[{'type':'page_publication_date','value':'2024-01-01','source':'meta'}]}, {'requested_url':'https://example.com/old','id':'old','status':'collected','page_dates':[{'type':'page_publication_date','value':'2008-11-17','source':'jsonld'}]}]}
 def test_oldest_dates_first_and_unknown_last(self):
  result=rank_sources(self.pages(),self.evidence(),{'sources':[]})
  self.assertEqual([p['title'] for p in result['pages']],['Old','New','Unknown'])
  self.assertEqual(result['pages'][0]['publication_date_source'],'jsonld')
 def test_conflicting_or_modified_dates_not_original_dates(self):
  evidence=self.evidence();evidence['pages'][1]['page_dates'].append({'type':'page_publication_date','value':'2010-02-03','source':'other'})
  evidence['pages'][0]['page_dates']=[{'type':'page_modified_date','value':'2000-01-01'}]
  result=rank_sources(self.pages(),evidence,{'sources':[]})
  self.assertTrue(all(p['publication_date'] is None for p in result['pages']))
  self.assertEqual(next(p for p in result['pages'] if p['title']=='Old')['date_status'],'conflicting_metadata')
 def test_identity_only_explicit_exact_domain_mapping(self):
  result=rank_sources(self.pages()+[{'url':'https://example.com.evil.test/story','title':'Impersonation'}],self.evidence(),{'sources':[]},[{'domain':'example.com','label':'Example Company'}])
  official=[p for p in result['pages'] if p['publisher_origin']['status']=='configured_official_domain']
  self.assertEqual(len(official),1);self.assertEqual(official[0]['title'],'Old')
  self.assertIsNone(official[0]['evidence_support_score'])
 def test_future_and_invalid_dates_not_used(self):
  evidence=self.evidence();evidence['pages'][0]['page_dates']=[{'type':'page_publication_date','value':'2099-01-01'}];evidence['pages'][1]['page_dates']=[{'type':'page_publication_date','value':'nonsense'}]
  result=rank_sources(self.pages(),evidence,{'sources':[]})
  self.assertTrue(all(p['publication_date'] is None for p in result['pages']))
 def test_support_score_and_origin_remain_separate(self):
  result=rank_sources(self.pages(),self.evidence(),{'sources':[{'id':'old','score':95}]})
  old=result['pages'][0];self.assertEqual(old['evidence_support_score'],95);self.assertEqual(old['publisher_origin']['status'],'unverified')
