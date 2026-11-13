from io import BytesIO
import unittest
from unittest.mock import patch
import cv2
import numpy as np
from test_remaining_stages import pattern
from visual import compare
from scene_integrity import scene_differences
from text_integrity import upload_assessment

def png(img):return cv2.imencode('.png',img)[1].tobytes()
def check(q,r):
 q,r=png(q),png(r)
 return scene_differences(q,r,compare(q,r,draw=False).get('alignment'))

class SceneTests(unittest.TestCase):
 def test_local_replacement_without_text_is_detected(self):
  ref=pattern();query=ref.copy();query[120:210,240:330]=[35,60,180]
  result=check(query,ref)
  self.assertEqual(result['status'],'differences_found',result)
  self.assertTrue(result['preview'])
  score=upload_assessment([{'scene_comparison':result,'comparison':{'status':'inconclusive','regions':[]}}])
  self.assertLessEqual(score['score'],35)
 def test_unchanged_and_jpeg_compression_do_not_flag(self):
  ref=pattern()
  result=check(ref,ref)
  self.assertEqual(result['status'],'consistent_in_overlap')
  compressed=cv2.imdecode(cv2.imencode('.jpg',ref,[cv2.IMWRITE_JPEG_QUALITY,70])[1],cv2.IMREAD_COLOR)
  self.assertEqual(check(compressed,ref)['status'],'consistent_in_overlap')
 def test_global_brightness_is_not_called_a_local_edit(self):
  ref=pattern();brighter=np.clip(ref.astype(float)*.9+15,0,255).astype(np.uint8)
  result=check(brighter,ref)
  self.assertNotEqual(result['status'],'differences_found',result)
 def test_no_alignment_unrelated_unknown(self):
  ref=pattern();result=scene_differences(png(ref),png(pattern(982)),None)
  self.assertEqual(result['status'],'inconclusive')
  self.assertIsNone(upload_assessment([{'scene_comparison':result}])['score'])
 def test_face_overlap_is_an_area_label_not_identity(self):
  ref=pattern();query=ref.copy();query[120:210,240:330]=[35,60,180]
  with patch('scene_integrity.face_boxes',return_value=[[240,120,90,90]]):result=check(query,ref)
  self.assertTrue(any(r['kind']=='face_area_difference' for r in result['regions']))
 def test_crop_does_not_mark_nonoverlap_as_change(self):
  ref=pattern();query=ref[60:420,70:570]
  result=check(query,ref)
  self.assertNotEqual(result['status'],'differences_found',result)
 def test_no_text_visual_agreement_has_bounded_score(self):
  ref=pattern();result=check(ref,ref)
  item={'scene_comparison':result}
  score=upload_assessment([item]);self.assertIsNotNone(score['score']);self.assertLessEqual(score['score'],80)
  self.assertEqual(score['score'],upload_assessment([item,item])['score'])
