from io import BytesIO
import unittest
from unittest.mock import AsyncMock, patch

import cv2
from fastapi.testclient import TestClient
import numpy as np
from PIL import Image

import server
from visual import compare, ACCEPTED
from context_report import context_report


def pattern(seed=42):
    random = np.random.default_rng(seed)
    image = np.full((480, 640, 3), 230, np.uint8)
    for i in range(90):
        x, y = random.integers([5, 5], [620, 460])
        color = tuple(int(v) for v in random.integers(15, 200, 3))
        cv2.circle(image, (int(x), int(y)), int(random.integers(4, 24)), color, -1)
        cv2.putText(image, str(i), (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX, .4, (15, 15, 15), 1)
    cv2.putText(image, 'SYNTHETIC DEMO FIXTURE', (30, 250), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 0, 0), 2)
    return image


def png(image):
    return cv2.imencode('.png', image)[1].tobytes()


class VisualTests(unittest.TestCase):
    def test_exact_and_crop_correspondence(self):
        reference = pattern()
        self.assertEqual(compare(png(reference), png(reference))['status'], 'exact_pixels')
        result = compare(png(reference[60:420, 70:570]), png(reference))
        self.assertEqual(result['status'], 'strong_correspondence', result)
        self.assertGreater(result['query_coverage'], .9)
        self.assertLess(result['reference_coverage'], .8)
        self.assertTrue(result['preview'].startswith('data:image/jpeg;base64,'))

    def test_recompressed_copy_and_canvas_derivative(self):
        reference = pattern()
        jpeg = cv2.imencode('.jpg', reference, [cv2.IMWRITE_JPEG_QUALITY, 65])[1].tobytes()
        self.assertIn(compare(jpeg, png(reference))['status'], ACCEPTED)
        canvas = np.full((650, 800, 3), 245, np.uint8)
        canvas[80:560, 80:720] = reference
        result = compare(png(canvas), png(reference))
        self.assertEqual(result['status'], 'strong_correspondence', result)
        self.assertLess(result['query_coverage'], .8)

    def test_unrelated_and_small_region_do_not_pass(self):
        reference = pattern()
        unrelated = pattern(982)
        self.assertNotIn(compare(png(unrelated), png(reference))['status'], ACCEPTED)
        unrelated[:70, :90] = reference[:70, :90]
        self.assertNotIn(compare(png(unrelated), png(reference))['status'], ACCEPTED)


class ContextTests(unittest.TestCase):
    def evidence(self, credit='Photo: Agency', date='2020-01-01'):
        return {'pages': [{'id': 'source-one', 'status': 'collected', 'requested_url': 'https://example.com/article',
            'final_url': 'https://example.com/article', 'title': 'Archive',
            'article_author': 'Journalist who is not the photographer',
            'page_dates': [{'value': date, 'type': 'page_publication_date', 'source': 'meta'}],
            'image_associations': [{'image_url': 'https://example.com/photo.jpg', 'association': 'image_element_located',
                                    'caption': 'Rescue exercise. Location: Mangaluru | Captured on 2018-04-03', 'reported_credit': credit}]}]}

    def test_report_quotes_sources_and_does_not_use_page_date_as_capture(self):
        report = context_report(self.evidence(), [{'image_url': 'https://example.com/photo.jpg', 'status': 'strong_correspondence'}])
        self.assertEqual(report['fields']['source']['value'], 'Photo: Agency')
        self.assertEqual(report['fields']['source']['status'], 'reported')
        self.assertEqual(report['fields']['date']['value'], '2018-04-03')
        self.assertEqual(report['publication_observations'][0]['value'], '2020-01-01')
        self.assertEqual(report['fields']['location']['value'], 'Mangaluru')
        self.assertEqual(report['fields']['source']['claims'][0]['evidence_id'], 'source-one')

    def test_unverified_claims_stay_candidates_and_missing_fields_unknown(self):
        data = self.evidence()
        data['pages'][0]['image_associations'][0]['caption'] = 'An image without an explicit date or location.'
        report = context_report(data, [])
        self.assertEqual(report['fields']['source']['status'], 'candidate')
        self.assertEqual(report['fields']['date']['status'], 'unknown')
        self.assertEqual(report['fields']['location']['status'], 'unknown')
        self.assertEqual(report['prior_use']['status'], 'candidate')

    def test_conflicting_credits_are_preserved(self):
        data = self.evidence()
        second = self.evidence(credit='Photo: Other Agency')['pages'][0]
        second = {**second, 'id': 'source-two'}
        data['pages'].append(second)
        report = context_report(data, [{'image_url': 'https://example.com/photo.jpg', 'status': 'exact_pixels'}])
        self.assertEqual(report['fields']['source']['status'], 'multiple_reports')
        self.assertIsNone(report['fields']['source']['value'])
        self.assertEqual(len(report['fields']['source']['claims']), 2)


class RemainingEndpointTests(unittest.TestCase):

    def test_server_owned_case_builds_cited_export_and_ignores_forged_pages(self):
        sample = ContextTests().evidence()
        server.cases.clear()
        search = {'pages': [{'url': 'https://example.com/real-source', 'full_matches': [{'url': 'https://example.com/photo.jpg'}], 'partial_matches': []}],
                  'full_matches': [], 'partial_matches': [], 'similar_images': [], 'labels': [], 'web_entities': []}
        with patch('server.read_key', return_value='test-key'), patch('server.google_search', new_callable=AsyncMock, return_value=search), \
             patch('server.verify_candidates', new_callable=AsyncMock, return_value=[{'image_url': 'https://example.com/photo.jpg', 'status': 'strong_correspondence'}]), \
             patch('server.collect_evidence', new_callable=AsyncMock, return_value=sample) as collector:
            client = TestClient(server.app)
            response = client.post('/api/search', files={'file': ('test.png', png(pattern()), 'image/png')})
            self.assertEqual(response.status_code, 200)
            identifier = response.json()['case_id']
            evidence = client.post('/api/evidence', json={'case_id': identifier, 'pages': [{'url': 'https://forged.example'}]})
            self.assertEqual(evidence.status_code, 200)
            self.assertEqual(collector.call_args.args[0][0]['url'], 'https://example.com/real-source')
            download = client.get('/api/reports/' + identifier)
            self.assertEqual(download.status_code, 200)
            self.assertEqual(download.json()['report']['fields']['source']['status'], 'reported')
            self.assertIn('attachment', download.headers['content-disposition'])
            self.assertEqual(client.get('/api/reports/missing').status_code, 404)
        server.cases.clear()

    def test_billing_error_is_explicit(self):
        import httpx
        adapter = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(403, json={
            'error': {'details': [{'reason': 'BILLING_DISABLED'}]}})))
        with patch('server.read_key', return_value='test-key'), patch('server.httpx.AsyncClient', return_value=adapter):
            response = TestClient(server.app).post('/api/search', files={'file': ('test.png', png(pattern()), 'image/png')})
        self.assertEqual(response.status_code, 502)
        self.assertIn('billing is disabled', response.json()['detail'])
