from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import unittest
from unittest.mock import AsyncMock, patch

import c2pa
import cv2
import numpy as np
from PIL import Image
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from fastapi.testclient import TestClient

from assessment import assess
from context_report import context_report
from media_checks import analyze_image, analyze_text, c2pa_check, legacy_watermark_check, LEGACY_PAYLOAD
from vendor.legacy_watermark.maxDct import EmbedMaxDct
import server


def image_bytes(array):
    stream = BytesIO()
    Image.fromarray(array).save(stream, 'PNG')
    return stream.getvalue()


def source(identifier='one', domain='example.com', credit='Photo: Agency'):
    return {'id': identifier, 'status': 'collected', 'requested_url': f'https://{domain}/article',
            'retrieved_at': '2026-01-01T00:00:00Z', 'article_author': 'Article journalist',
            'page_dates': [{'type': 'page_publication_date', 'value': '2025-01-01', 'source': 'meta'}],
            'image_associations': [{'image_url': 'https://images.example/photo.png',
                'association': 'image_element_located', 'caption': 'A rescue exercise', 'reported_credit': credit}]}


def assessment(pages, checks=None):
    evidence = {'pages': pages}
    checks = checks if checks is not None else [{'image_url': 'https://images.example/photo.png', 'status': 'exact_pixels'}]
    return assess(evidence, checks, context_report(evidence, checks), ['https://images.example/unchecked.png'])


class AssessmentTests(unittest.TestCase):
    def test_weights_and_unknown_reliability_are_explicit(self):
        result = assessment([source()])
        self.assertEqual(result['sources'][0]['score'], 88)
        self.assertEqual(result['overall']['score'], 75)
        self.assertEqual(sum(result['source_weights'].values()), 100)
        self.assertIsNone(result['source_reliability']['score'])
        self.assertIsNone(result['visual_items'][-1]['score'])
        self.assertIn('image_context', [f['name'] for f in result['sources'][0]['factors'] if f['points'] < f['weight']])

    def test_no_visual_match_means_unknown_overall_not_fake(self):
        result = assessment([source()], [])
        self.assertIsNone(result['overall']['score'])
        self.assertEqual(result['overall']['status'], 'insufficient_evidence')
        self.assertIsNone(assessment([{'requested_url': 'https://example.com', 'status': 'blocked'}])['sources'][0]['score'])

    def test_byline_and_page_date_are_not_photographer_or_capture_date(self):
        page = source(credit=None)
        result = assessment([page])
        factors = {f['name']: f['points'] for f in result['sources'][0]['factors']}
        self.assertEqual(factors['attribution'], 0)
        self.assertEqual(factors['image_context'], 3)
        author = next(i for i in result['evidence_items'] if i['kind'] == 'article_author')
        self.assertEqual(author['scope'], 'page')

    def test_copies_same_domain_and_shared_credit_do_not_inflate_agreement(self):
        pages = [source(), source('two', 'other.org'), source('three', 'news.example.com')]
        result = assessment(pages)
        self.assertEqual(len(result['corroboration_groups']), 1)
        self.assertEqual(result['overall']['independent_agreement_bonus'], 0)
        self.assertEqual(result['overall']['score'], assessment(pages[:1])['overall']['score'])

    def test_duplicate_text_is_grouped_without_shared_credit(self):
        pages = [source(), source('two', 'other.org', 'Photo: Other')]
        for page in pages:
            page['text'] = ' '.join(f'word{i}' for i in range(60))
        result = assessment(pages)
        self.assertEqual(len(result['corroboration_groups']), 1)
        self.assertEqual(result['overall']['unresolved_difference_penalty'], 5)
        self.assertIn('source', result['overall']['unresolved_fields'])

    def test_agreement_only_from_separate_groups_on_same_kind_claim(self):
        pages = [source(), source('two', 'other.org', 'Photo: Other')]
        for page in pages:
            page['image_metadata'] = [{'image_url': 'https://images.example/photo.png', 'date_created': '2018-02-03'}]
        result = assessment(pages)
        self.assertEqual(result['overall']['independent_agreement_bonus'], 5)
        self.assertEqual(result['overall']['unresolved_difference_penalty'], 5)

    def test_unassociated_image_cannot_lend_its_credit_or_visual_points(self):
        page = source()
        page['image_associations'][0]['association'] = 'not_located'
        result = assessment([page])
        self.assertFalse(result['sources'][0]['visual_support'])
        self.assertIsNone(result['overall']['score'])


class MediaTests(unittest.TestCase):
    def test_real_legacy_marker_positive_and_negative(self):
        rgb = np.random.default_rng(17).integers(50, 205, (512, 512, 3), dtype=np.uint8)
        self.assertEqual(legacy_watermark_check(rgb)['status'], 'not_detected')
        bits = np.unpackbits(np.frombuffer(LEGACY_PAYLOAD, dtype=np.uint8))
        marked = EmbedMaxDct(watermarks=bits, wmLen=len(bits)).encode(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        self.assertEqual(legacy_watermark_check(cv2.cvtColor(marked, cv2.COLOR_BGR2RGB))['status'], 'detected')
        self.assertEqual(legacy_watermark_check(rgb[:100])['status'], 'unsupported')

    def test_measured_dimensions_colors_and_blur_are_not_ai_verdicts(self):
        rgb = np.full((120, 240, 3), [255, 0, 0], dtype=np.uint8)
        result = analyze_image(image_bytes(rgb))
        measured = result['measurements']
        self.assertEqual(measured['oriented_dimensions'], [240, 120])
        self.assertEqual(measured['aspect_ratio'], '2:1')
        self.assertEqual(measured['mean_rgb'], [255., 0., 0.])
        self.assertEqual(measured['laplacian_variance'], 0)
        self.assertEqual(result['semantic_analysis']['status'], 'not_run')
        self.assertEqual(result['watermark_checks'][0]['status'], 'not_detected')
        self.assertFalse(result['watermark_checks'][2]['ran'])

    def test_transparency_does_not_run_modified_pixels_through_detector(self):
        rgba = np.zeros((256, 256, 4), dtype=np.uint8)
        result = analyze_image(image_bytes(rgba))
        self.assertEqual(result['measurements']['mean_rgb'], [255., 255., 255.])
        self.assertEqual(result['measurements']['transparent_pixel_fraction'], 1)
        self.assertEqual(result['watermark_checks'][1]['status'], 'unsupported')
        self.assertFalse(result['watermark_checks'][1]['ran'])

    def test_text_formatting_is_measured_without_origin_claim(self):
        result = analyze_text('ordinary\u200b text\u200d')
        self.assertEqual(result['measurements']['invisible_format_character_counts']['zero_width_space'], 1)
        self.assertTrue(all(not check['ran'] for check in result['watermark_checks']))
        self.assertEqual(result['watermark_checks'][0]['status'], 'unavailable')

    def test_real_signed_credential_is_detected_but_not_trusted(self):
        # Ephemeral test-only key: never written to disk or used as a trust anchor.
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Untrusted local test')])
        ca_key = ec.generate_private_key(ec.SECP256R1())
        ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Untrusted test CA')])
        now = datetime.now(timezone.utc)
        ca_cert = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=2))
                .not_valid_after(now+timedelta(days=2))
                .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
                .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
                .sign(ca_key, hashes.SHA256()))
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(ca_name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1))
                .not_valid_after(now+timedelta(days=1))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=True)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
                .sign(ca_key, hashes.SHA256()))
        pem = (cert.public_bytes(serialization.Encoding.PEM)+ca_cert.public_bytes(serialization.Encoding.PEM)).decode()
        manifest = {'claim_generator': 'local-test/1', 'format': 'image/png', 'title': 'Test only',
            'assertions': [{'label': 'c2pa.actions', 'data': {'actions': [{'action': 'c2pa.created',
                'digitalSourceType': 'http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia'}]}}]}
        config = {'verify': {'verify_after_sign': False}, 'core': {'allowed_network_hosts': []}}
        signed = BytesIO()
        with c2pa.Context.from_dict(config) as ctx:
            with c2pa.Signer.from_callback(lambda data: key.sign(data, ec.ECDSA(hashes.SHA256())), c2pa.C2paSigningAlg.ES256, pem) as signer:
                with c2pa.Builder.from_json(json.dumps(manifest), context=ctx) as builder:
                    builder.sign(signer, 'image/png', BytesIO(image_bytes(np.zeros((32,32,3), np.uint8))), signed)
        result = c2pa_check(signed.getvalue(), 'image/png')
        self.assertEqual(result['status'], 'detected', result)
        self.assertEqual(result['trust'], 'not_established', result)
        self.assertEqual(result['ai_involvement_claim'], 'declared_in_manifest')
        # Original bytes retain the manifest; a normal pixel-only resave loses it.
        with Image.open(BytesIO(signed.getvalue())) as image:
            stripped = image_bytes(np.asarray(image.convert('RGB')))
        self.assertEqual(c2pa_check(stripped, 'image/png')['status'], 'not_detected')


class LocalEndpointsTests(unittest.TestCase):

    def test_analysis_uses_original_bytes_and_export_preserves_assessment(self):
        content = image_bytes(np.zeros((32,64,3), np.uint8))
        empty_search = {'pages': [], 'full_matches': [], 'partial_matches': [], 'similar_images': [], 'labels': [], 'web_entities': []}
        with patch('server.read_key', return_value='secret-do-not-export'), patch('server.google_search', new_callable=AsyncMock, return_value=empty_search), patch('server.verify_candidates', new_callable=AsyncMock, return_value=[]), patch('server.analyze_image', return_value={'original_byte_check': True}) as analyze:
            client = TestClient(server.app)
            response = client.post('/api/search', files={'file': ('sample.png', content, 'image/png')})
            self.assertEqual(response.status_code, 200)
            exported = client.get('/api/reports/'+response.json()['case_id'])
        analyze.assert_called_once_with(content)
        self.assertEqual(exported.json()['image_analysis'], {'original_byte_check': True})
        self.assertIsNone(exported.json()['report']['assessment']['overall']['score'])
        self.assertNotIn('secret-do-not-export', exported.text)
