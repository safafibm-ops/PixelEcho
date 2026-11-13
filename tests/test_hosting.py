import unittest
from unittest.mock import patch
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.trustedhost import TrustedHostMiddleware
from hosting import deployment_settings, same_origin
import deploy

class HostingTests(unittest.TestCase):
 def test_local_defaults_and_render_auto_url(self):
  origin,hosts=deployment_settings({})
  self.assertEqual(origin,'');self.assertNotIn('*',hosts)
  origin,hosts=deployment_settings({'RENDER_EXTERNAL_URL':'https://pixelecho.onrender.com/'})
  self.assertEqual(origin,'https://pixelecho.onrender.com');self.assertIn('pixelecho.onrender.com',hosts)
 def test_custom_origin_override_and_normalized_default_port(self):
  origin,hosts=deployment_settings({'PUBLIC_ORIGIN':'https://PixelEcho.example:443/','RENDER_EXTERNAL_URL':'https://other.onrender.com'})
  self.assertEqual(origin,'https://pixelecho.example');self.assertIn('pixelecho.example',hosts)
  self.assertNotIn('other.onrender.com',hosts)
 def test_invalid_configuration_fails_closed(self):
  for value in ['https://example.com/path','https://user:secret@example.com','https://example.com?x=1','https://example.com#x','*','file:///tmp','https://example.com:wrong']:
   with self.subTest(value=value),self.assertRaises(RuntimeError):deployment_settings({'PUBLIC_ORIGIN':value})
 def test_same_origin_https_proxy_and_cross_origin(self):
  self.assertTrue(same_origin('https://pixelecho.onrender.com','http://pixelecho.onrender.com/','https://pixelecho.onrender.com'))
  self.assertFalse(same_origin('https://evil.example','http://pixelecho.onrender.com/','https://pixelecho.onrender.com'))
  self.assertFalse(same_origin('http://pixelecho.onrender.com','http://pixelecho.onrender.com/','https://pixelecho.onrender.com'))
  self.assertTrue(same_origin('http://127.0.0.1:8000','http://127.0.0.1:8000/',''))
  self.assertFalse(same_origin('http://127.0.0.1:9000','http://127.0.0.1:8000/',''))
 def test_actual_trusted_host_middleware(self):
  origin,hosts=deployment_settings({'PUBLIC_ORIGIN':'https://pixelecho.example'})
  app=FastAPI();app.add_middleware(TrustedHostMiddleware,allowed_hosts=hosts)
  @app.get('/')
  def home():return {'ok':True}
  self.assertEqual(TestClient(app,base_url='https://pixelecho.example').get('/').status_code,200)
  self.assertEqual(TestClient(app,base_url='https://evil.example').get('/').status_code,400)
 def test_hosted_start_uses_port_and_single_worker(self):
  with patch.dict('os.environ',{'PORT':'12345'}),patch('deploy.uvicorn.run') as run:deploy.main()
  run.assert_called_once_with('server:app',host='0.0.0.0',port=12345,workers=1,proxy_headers=False)
 def test_bad_port_rejected(self):
  with patch.dict('os.environ',{'PORT':'nope'}),self.assertRaises(RuntimeError):deploy.main()
