"""Local measurements and explicitly scoped watermark/provenance checks."""
from collections import Counter
from io import BytesIO
import json
import math
import re
import warnings

import cv2
import numpy as np
from PIL import Image, ImageOps

LEGACY_PAYLOAD = b'StableDiffusionV1'
METHODS = {
    'c2pa': 'https://github.com/contentauth/c2pa-python/blob/main/docs/usage.md',
    'legacy_sd': 'https://github.com/CompVis/stable-diffusion/blob/main/scripts/txt2img.py',
    'synthid_image': 'https://blog.google/innovation-and-ai/models-and-research/google-deepmind/synth-id-ai-content/',
    'synthid_text': 'https://github.com/google-deepmind/synthid-text',
}


def c2pa_check(content, mime):
    check = {'id': 'c2pa', 'name': 'Embedded C2PA Content Credentials', 'kind': 'provenance',
             'status': 'unavailable', 'ran': False, 'source': METHODS['c2pa'],
             'note': 'Signed provenance is distinct from an invisible pixel watermark. Missing credentials do not establish human origin.'}
    try:
        import c2pa
    except (ImportError, OSError):
        return {**check, 'reason': 'The C2PA reader or native runtime is unavailable.'}
    try:
        config = {'verify': {'remote_manifest_fetch': False, 'ocsp_fetch': False,
                             'verify_trust': True, 'verify_timestamp_trust': True,
                             'verify_after_reading': True}, 'core': {'allowed_network_hosts': []}}
        with c2pa.Context.from_dict(config) as context:
            with c2pa.Reader(mime, BytesIO(content), context=context) as reader:
                data = json.loads(reader.json())
        active = data.get('manifests', {}).get(data.get('active_manifest'), {})
        if not active:
            return {**check, 'status': 'not_detected', 'ran': True, 'reason': 'No active embedded manifest was returned. Remote credential discovery was disabled.'}
        source_types = []
        labels = []
        for assertion in active.get('assertions', [])[:100]:
            label = assertion.get('label', '')
            if isinstance(label, str):
                labels.append(label[:120])
            if label.startswith('c2pa.actions'):
                for action in assertion.get('data', {}).get('actions', [])[:100]:
                    source_type = action.get('digitalSourceType')
                    if isinstance(source_type, str):
                        source_types.append(source_type[:300])
        codes = set()
        def read_codes(value, depth=0):
            if depth > 8:
                return
            if isinstance(value, dict):
                if isinstance(value.get('code'), str):
                    codes.add(value['code'][:120])
                for child in list(value.values())[:100]:
                    read_codes(child, depth+1)
            elif isinstance(value, list):
                for child in value[:100]:
                    read_codes(child, depth+1)
        read_codes(data.get('validation_status', []))
        read_codes(data.get('validation_results', {}))
        state = str(data.get('validation_state') or 'not_reported')[:80]
        ai = any(value.rsplit('/', 1)[-1] in ('trainedAlgorithmicMedia', 'compositeWithTrainedAlgorithmicMedia') for value in source_types)
        return {**check, 'status': 'detected', 'ran': True, 'reason': 'An embedded manifest is present; inspect validation and the scope of its claims.',
                'validation_state': state, 'trust': 'sdk_reports_trusted' if state.casefold() == 'trusted' else 'not_established',
                'validation_codes': sorted(codes)[:40], 'assertion_labels': labels,
                'digital_source_types': source_types, 'ai_involvement_claim': 'declared_in_manifest' if ai else 'not_declared_in_checked_actions',
                'ai_claim_note': 'A declaration is reported, not a universal AI verdict. Presence does not imply a valid or trusted signature. Offline checks do not include fresh revocation or remote manifests.'}
    except c2pa.C2paError.ManifestNotFound:
        return {**check, 'status': 'not_detected', 'ran': True, 'reason': 'No embedded C2PA manifest found. Remote lookup was not run.'}
    except Exception:
        return {**check, 'ran': True, 'reason': 'The reader could not safely parse or validate this credential. The result is unavailable, not absent.'}


def legacy_watermark_check(rgb):
    height, width = rgb.shape[:2]
    check = {'id': 'legacy_sd', 'name': 'Legacy Stable Diffusion V1 dwtDct marker', 'kind': 'pixel_watermark',
             'status': 'unsupported', 'ran': False, 'source': METHODS['legacy_sd'],
             'note': 'Checks only the exact public StableDiffusionV1 marker. Anyone can copy this marker; it is not an authenticated generator or creator claim.'}
    if min(width, height) < 256 or width * height > 4_000_000:
        return {**check, 'reason': 'This local check requires both dimensions at least 256 px and at most 4 megapixels. The original is not resized for detection.'}
    try:
        from vendor.legacy_watermark.maxDct import EmbedMaxDct
        decoded = EmbedMaxDct(watermarks=[], wmLen=len(LEGACY_PAYLOAD)*8).decode(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        matched = np.packbits(np.asarray(decoded, dtype=np.uint8)).tobytes() == LEGACY_PAYLOAD
        return {**check, 'status': 'detected' if matched else 'not_detected', 'ran': True,
                'reason': 'The exact 136-bit legacy payload matched.' if matched else 'The exact legacy payload was not recovered. This does not rule out AI generation or other watermarks.',
                'limitations': 'Compression, crops, screenshots, and flat-color content may weaken detection. No false-positive probability is claimed.'}
    except (ImportError, OSError):
        return {**check, 'status': 'unavailable', 'reason': 'The local frequency decoder dependencies are unavailable.'}
    except Exception:
        return {**check, 'status': 'unavailable', 'ran': True, 'reason': 'The legacy marker check could not complete on this image.'}


def analyze_image(content):
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(BytesIO(content)) as image:
            if image.format not in ('JPEG', 'PNG') or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('Use a single JPEG or PNG image.')
            if image.width * image.height > 20_000_000:
                raise ValueError('Image exceeds the 20 megapixel limit.')
            raw_dimensions = list(image.size)
            format_name = image.format
            mime = Image.MIME[format_name]
            image.load()
            original_rgb = np.asarray(image.convert('RGB')) if image.width * image.height <= 4_000_000 else None
            oriented = ImageOps.exif_transpose(image)
            transparent = 'A' in oriented.getbands() or 'transparency' in image.info
            width, height = oriented.size
            # Transparency is composited onto white for measurements; no colors
            # from invisible pixels are treated as visible image characteristics.
            if transparent:
                rgba = oriented.convert('RGBA')
                alpha = np.asarray(rgba.getchannel('A'))
                transparent_fraction = float((alpha < 255).mean())
                visible = Image.new('RGBA', rgba.size, 'white')
                visible.alpha_composite(rgba)
                visible = visible.convert('RGB')
            else:
                transparent_fraction = 0
                visible = oriented.convert('RGB')
            measured = visible.copy()
            measured.thumbnail((1024, 1024))
            rgb = np.asarray(measured)
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            histogram = np.bincount(gray.ravel(), minlength=256).astype(float)
            probabilities = histogram[histogram > 0] / gray.size
            palette_image = measured.resize((min(128, measured.width), min(128, measured.height))).quantize(colors=5)
            palette = palette_image.getpalette()
            dominant = []
            for count, index in sorted(palette_image.getcolors() or [], reverse=True):
                color = palette[index*3:index*3+3]
                dominant.append({'hex': '#' + ''.join(f'{v:02x}' for v in color),
                                 'fraction': round(count/(palette_image.width*palette_image.height), 4)})
            common = math.gcd(width, height)
            measurements = {
                'format': format_name, 'file_bytes': len(content), 'stored_dimensions': raw_dimensions,
                'oriented_dimensions': [width, height], 'megapixels': round(width*height/1e6, 3),
                'aspect_ratio': f'{width//common}:{height//common}', 'aspect_ratio_decimal': round(width/height, 3),
                'analysis_dimensions': [measured.width, measured.height],
                'mean_rgb': [round(float(value), 1) for value in rgb.mean(axis=(0, 1))], 'dominant_colors': dominant,
                'mean_luminance_0_255': round(float(gray.mean()), 2), 'luminance_stddev': round(float(gray.std()), 2),
                'near_black_fraction': round(float((gray <= 10).mean()), 4),
                'near_white_fraction': round(float((gray >= 245).mean()), 4),
                'laplacian_variance': round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2),
                'edge_fraction': round(float((cv2.Canny(gray, 50, 150) > 0).mean()), 4),
                'grayscale_entropy_bits': round(float(-np.sum(probabilities*np.log2(probabilities))), 3),
                'transparent_pixel_fraction': round(transparent_fraction, 4),
            }
    legacy = legacy_watermark_check(original_rgb) if original_rgb is not None and not transparent_fraction else {
        'id': 'legacy_sd', 'name': 'Legacy Stable Diffusion V1 dwtDct marker', 'kind': 'pixel_watermark',
        'status': 'unsupported', 'ran': False, 'source': METHODS['legacy_sd'],
        'reason': 'Original exceeds the 4 megapixel local decoder budget. It was not resized for a watermark verdict.'}
    if transparent_fraction:
        legacy = {**legacy, 'status': 'unsupported', 'ran': False,
                  'reason': 'Transparent inputs are unsupported by this legacy watermark profile; background compositing changes pixels.'}
    checks = [c2pa_check(content, mime), legacy,
              {'id': 'synthid_image', 'name': 'SynthID image watermark', 'kind': 'pixel_watermark',
               'status': 'unavailable', 'ran': False, 'source': METHODS['synthid_image'],
               'reason': 'Automatic SynthID detection is unavailable in PixelEcho. Use the official detector manually; Google Vision and Serper do not detect SynthID.',
               'note': 'No image is sent to the manual detector by PixelEcho. Its external result is not imported or verified here. A missing watermark does not prove human origin.',
               'manual_url': 'https://synthid.com/'}]
    return {'measurements': measurements, 'watermark_checks': checks,
            'measurement_notes': [
                'All listed attributes are measured technical characteristics; no semantic model inference or AI-origin classification ran.',
                'Statistics use the oriented analysis image at at most 1024 px per side. Sharpness depends on scale, texture, noise, and subject; no universal blur threshold is applied.',
                'Near-black/white fractions and entropy are descriptors, not proof of poor quality, manipulation, or generation.',
                'Transparency is composited onto white for color and sharpness measurements. ICC color conversion is not performed.',
                'Provenance is read from the original bytes before JPEG normalization. Detector absence or non-detection does not prove human origin.',
                'Legacy watermark decoding uses stored pixels before EXIF orientation; measurements use the oriented display image.',
            ], 'semantic_analysis': {'status': 'not_run', 'reason': 'No object, face, location, or scene recognition model is loaded.'}}


def analyze_text(text):
    counts = Counter(text)
    formats = {'zero_width_space': counts['\u200b'], 'zero_width_non_joiner': counts['\u200c'],
               'zero_width_joiner': counts['\u200d'], 'word_joiner': counts['\u2060'], 'byte_order_mark': counts['\ufeff']}
    return {'measurements': {'characters': len(text), 'words': len(re.findall(r'\b\w+\b', text)),
                             'invisible_format_character_counts': formats},
            'watermark_checks': [
                {'id': 'synthid_text', 'name': 'SynthID Text statistical watermark', 'status': 'unavailable', 'ran': False,
                 'source': METHODS['synthid_text'],
                 'reason': 'Detection requires the generator-matching secret configuration and tokenizer. Neither is configured; no text was sent to an external detector.'},
                {'id': 'text_credentials', 'name': 'C2PA in pasted plain text', 'status': 'unsupported', 'ran': False,
                 'reason': 'Pasted plain text does not provide the signed media container needed by this image credential reader.'},
            ], 'note': 'Unicode formatting characters can occur in ordinary writing and many languages. Their presence is not an AI watermark verdict. No universal AI-text detector ran.'}

