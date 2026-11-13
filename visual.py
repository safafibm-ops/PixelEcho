"""Conservative visual correspondence checks; scores are not authenticity probabilities."""
import asyncio
import base64
from io import BytesIO
import warnings

import cv2
import numpy as np
from PIL import Image, ImageOps

from evidence import SafeFetcher, EvidenceError

cv2.setNumThreads(1)
ACCEPTED = {'exact_pixels', 'strong_correspondence'}


def decode(content):
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > 20_000_000 or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('Image exceeds analysis limits')
            image = ImageOps.exif_transpose(image).convert('RGB')
            image.thumbnail((1400, 1400))
            return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


def compare(query_bytes, reference_bytes, *, draw=True):
    query, reference = decode(query_bytes), decode(reference_bytes)
    base = {'status': 'inconclusive', 'inliers': 0, 'inlier_ratio': 0,
            'query_coverage': 0, 'reference_coverage': 0,
            'aligned_error': None, 'preview': None,
            'policy': 'prototype_sift_v1_uncalibrated',
            'notice': 'Visual correspondence only. This does not prove identity, chronology, authenticity, or that every pixel is unchanged.'}
    if query.shape == reference.shape and np.array_equal(query, reference):
        base.update(status='exact_pixels', query_coverage=1, reference_coverage=1, aligned_error=0)
        return base
    sift = cv2.SIFT_create(nfeatures=1800)
    qk, qd = sift.detectAndCompute(cv2.cvtColor(query, cv2.COLOR_BGR2GRAY), None)
    rk, rd = sift.detectAndCompute(cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY), None)
    if qd is None or rd is None or len(qk) < 20 or len(rk) < 20:
        base['reason'] = 'Insufficient distinctive features; a negative origin conclusion cannot be drawn.'
        return base
    pairs = cv2.BFMatcher().knnMatch(qd, rd, k=2)
    good = sorted([pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < .72 * pair[1].distance], key=lambda m: m.distance)
    used = set()
    matches = []
    for match in good:
        if match.trainIdx not in used:
            matches.append(match)
            used.add(match.trainIdx)
    if len(matches) < 20:
        base['reason'] = 'Not enough consistent candidate correspondences.'
        return base
    qp = np.float32([qk[m.queryIdx].pt for m in matches])
    rp = np.float32([rk[m.trainIdx].pt for m in matches])
    transform, selected = cv2.findHomography(rp, qp, cv2.RANSAC, 3, maxIters=2000)
    if transform is None or selected is None or not np.isfinite(transform).all() or abs(np.linalg.det(transform)) < 1e-10:
        base['reason'] = 'A stable geometric alignment could not be established.'
        return base
    selected = selected.ravel().astype(bool)
    count = int(selected.sum())
    ratio = count / len(matches)
    base.update(inliers=count, inlier_ratio=round(ratio, 3))
    qh, qw = query.shape[:2]
    rh, rw = reference.shape[:2]
    qspread = cv2.contourArea(cv2.convexHull(qp[selected])) / (qh * qw) if count >= 3 else 0
    rspread = cv2.contourArea(cv2.convexHull(rp[selected])) / (rh * rw) if count >= 3 else 0
    if count < 20 or ratio < .55 or qspread < .1 or rspread < .1:
        base['reason'] = 'Matching points are too few or concentrated in a small region.'
        return base
    support = cv2.warpPerspective(np.ones((rh, rw), np.uint8), transform, (qw, qh))
    inverse_support = cv2.warpPerspective(np.ones((qh, qw), np.uint8), np.linalg.inv(transform), (rw, rh))
    supported = cv2.erode(support, np.ones((7, 7), np.uint8)).astype(bool)
    base.update(query_coverage=round(float(support.mean()), 3), reference_coverage=round(float(inverse_support.mean()), 3))
    if supported.sum() < 500 or min(support.mean(), inverse_support.mean()) < .12:
        base['reason'] = 'Not enough overlapping image content was retained.'
        return base
    aligned = cv2.warpPerspective(reference, transform, (qw, qh))
    error = float(np.abs(query.astype(np.float32) - aligned.astype(np.float32))[supported].mean() / 255)
    base['aligned_error'] = round(error, 4)
    if error > .08:
        base['reason'] = 'Geometric points align but the overlapping pixels differ substantially.'
        return base
    base['status'] = 'strong_correspondence'
    base['reason'] = 'Distributed features and overlapping image content passed the prototype checks.'
    if draw:
        kept = [m for m, flag in zip(matches, selected) if flag][:25]
        preview = cv2.drawMatches(query, qk, reference, rk, kept, None,
                                  matchColor=(90, 175, 90), flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
        scale = min(1, 1100 / preview.shape[1])
        preview = cv2.resize(preview, None, fx=scale, fy=scale)
        ok, encoded = cv2.imencode('.jpg', preview, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ok:
            base['preview'] = 'data:image/jpeg;base64,' + base64.b64encode(encoded).decode('ascii')
    return base


async def verify_candidates(query_bytes, result, *, fetcher=None):
    fetcher = fetcher or SafeFetcher()
    candidates = []
    for page in result.get('pages', [])[:5]:
        candidates.extend(item['url'] for item in page.get('full_matches', []) + page.get('partial_matches', []))
    for group in ('full_matches', 'partial_matches', 'similar_images'):
        candidates.extend(item['url'] for item in result.get(group, []))
    candidates = list(dict.fromkeys(candidates))[:4]
    semaphore = asyncio.Semaphore(2)
    async def verify(url):
        try:
            async with semaphore, asyncio.timeout(10):
                code, final_url, content = await fetcher.fetch(url, image=True)
                if code != 200:
                    raise EvidenceError('unavailable', f'Image host returned HTTP {code}.')
                check = await asyncio.to_thread(compare, query_bytes, content, draw=False)
            return {'image_url': url, 'final_url': final_url, **check}
        except EvidenceError as error:
            return {'image_url': url, 'status': 'unavailable', 'reason': error.message}
        except TimeoutError:
            return {'image_url': url, 'status': 'unavailable', 'reason': 'Candidate image timed out.'}
        except Exception:
            return {'image_url': url, 'status': 'inconclusive', 'reason': 'The candidate could not be analyzed safely.'}
    return await asyncio.gather(*(verify(url) for url in candidates))
