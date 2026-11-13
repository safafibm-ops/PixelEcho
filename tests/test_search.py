import base64
from io import BytesIO
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
from PIL import Image

import server


def sample_png():
    data = BytesIO()
    Image.new('RGB', (24, 18), (80, 130, 90)).save(data, 'PNG')
    return data.getvalue()


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        verifier = patch('server.verify_candidates', new_callable=AsyncMock, return_value=[])
        verifier.start()
        self.addCleanup(verifier.stop)

    def upload(self, data=None, **kwargs):
        return self.client.post('/api/search', files={'file': ('sample.png', sample_png() if data is None else data, 'image/png')}, **kwargs)

    def test_missing_key_rejects_without_google_request(self):
        with patch('server.read_key', return_value=''), patch('server.google_search', new_callable=AsyncMock) as call:
            self.assertFalse(self.client.get('/api/status').json()['configured'])
            self.assertEqual(self.upload().status_code, 503)
            call.assert_not_called()

    def test_real_adapter_contract_normalizes_google_response(self):
        def handler(request):
            self.assertEqual(str(request.url), server.GOOGLE_ENDPOINT)
            self.assertEqual(request.headers['X-Goog-Api-Key'], 'unit-test-key')
            import json
            payload = json.loads(request.content)['requests'][0]
            self.assertEqual(payload['features'], [{'type': 'WEB_DETECTION', 'maxResults': 20}, {'type': 'TEXT_DETECTION'}])
            self.assertTrue(base64.b64decode(payload['image']['content']).startswith(b'\xff\xd8'))
            return httpx.Response(200, json={'responses': [{'webDetection': {
                'pagesWithMatchingImages': [{'url': 'https://example.com/source', 'pageTitle': 'A source', 'partialMatchingImages': [{'url': 'https://example.com/photo.jpg'}]}],
                'fullMatchingImages': [{'url': 'https://example.com/photo.jpg'}, {'url': 'https://example.com/photo.jpg'}],
                'webEntities': [{'description': 'Example entity'}],
            }}]})
        adapter_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch('server.read_key', return_value='unit-test-key'), patch('server.httpx.AsyncClient', return_value=adapter_client):
            result = self.upload()
        self.assertEqual(result.status_code, 200)
        body = result.json()
        self.assertEqual(body['provider_requests'], 1)
        self.assertEqual(body['query_dimensions'], [24, 18])
        self.assertEqual(len(body['full_matches']), 1)
        self.assertEqual(body['pages'][0]['title'], 'A source')
        self.assertNotIn('unit-test-key', result.text)

    def test_invalid_image_rejected_before_network(self):
        with patch('server.read_key', return_value='unit-test-key'), patch('server.google_search', new_callable=AsyncMock) as call:
            self.assertEqual(self.upload(b'not an image').status_code, 415)
            call.assert_not_called()

    def test_successful_empty_annotation_stays_empty(self):
        adapter_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'responses': [{}]})))
        with patch('server.read_key', return_value='unit-test-key'), patch('server.httpx.AsyncClient', return_value=adapter_client):
            result = self.upload()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['pages'], [])
        self.assertEqual(result.json()['full_matches'], [])

    def test_provider_error_does_not_echo_secrets(self):
        adapter_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(403, json={'error': {'message': 'unit-test-key should never be returned'}})))
        with patch('server.read_key', return_value='unit-test-key'), patch('server.httpx.AsyncClient', return_value=adapter_client):
            result = self.upload()
        self.assertEqual(result.status_code, 502)
        self.assertIn('billing', result.json()['detail'])
        self.assertNotIn('unit-test-key', result.text)

    def test_cross_origin_submission_rejected(self):
        with patch('server.read_key', return_value='unit-test-key'), patch('server.google_search', new_callable=AsyncMock) as call:
            self.assertEqual(self.upload(headers={'Origin': 'https://unrelated.example'}).status_code, 403)
            call.assert_not_called()

    def test_unsafe_returned_urls_removed(self):
        result = server.normalize({'fullMatchingImages': [{'url': 'javascript:alert(1)'}, {'url': 'https://example.com/p.jpg'}], 'pagesWithMatchingImages': [{'url': 'file:///secret'}]})
        self.assertEqual(result['pages'], [])
        self.assertEqual(result['full_matches'], [{'url': 'https://example.com/p.jpg'}])


if __name__ == '__main__':
    unittest.main()
