"""Stages 1 and 2: Google WEB_DETECTION and bounded webpage evidence collection.

The request structure follows the official Vision API and 5Pils detect_web:
vendor/5pils/scripts/collect_RIS_evidence.py (Apache-2.0).
These adapters are newly written for an interactive application. They do not
run the research scripts, download datasets, or generate contextual answers.
"""

import asyncio
import base64
from contextlib import asynccontextmanager
from io import BytesIO
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
import warnings
from uuid import uuid4

import httpx
import cv2
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from evidence import collect_evidence
from visual import verify_candidates, compare
from context_report import context_report
from assessment import assess
from investigation import observations, crop_photo, keyword_search, rank_pages, retrieve_passages
from evidence import SafeFetcher
from scene_integrity import scene_differences
from text_integrity import paragraphs, compare_text, upload_assessment
from media_checks import analyze_image

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 20_000_000
GOOGLE_ENDPOINT = 'https://vision.googleapis.com/v1/images:annotate'
PLACEHOLDER = 'PASTE_YOUR_GOOGLE_CLOUD_API_KEY_HERE'
search_lock = asyncio.Lock()
evidence_lock = asyncio.Lock()
cases = {}


def expire_cases():
    now = time.monotonic()
    for identifier in list(cases):
        if now - cases[identifier]['created'] > 900:
            del cases[identifier]
    while len(cases) > 8:
        del cases[next(iter(cases))]


def build_report(collected, verification, search=None):
    report = context_report(collected, verification)
    pages = list(collected.get('pages', []))
    represented = {page['requested_url'].split('#')[0] for page in pages}
    image_candidates = []
    for page in (search or {}).get('pages', []):
        image_candidates.extend(item['url'] for item in page.get('full_matches', []) + page.get('partial_matches', []))
        if page['url'].split('#')[0] not in represented:
            pages.append({'requested_url': page['url'], 'status': 'not_collected', 'title': page.get('title')})
            represented.add(page['url'].split('#')[0])
    for group in ('full_matches', 'partial_matches', 'similar_images'):
        image_candidates.extend(item['url'] for item in (search or {}).get(group, []))
    report['assessment'] = assess({**collected, 'pages': pages}, verification, report, image_candidates)
    return report


@asynccontextmanager
async def lifespan(app):
    yield


app = FastAPI(title='PixelEcho', lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')


def read_key():
    key = os.environ.get('GOOGLE_VISION_API_KEY', '').strip()
    if not key:
        try:
            config = json.loads((ROOT / 'config.local.json').read_text(encoding='utf-8-sig'))
            value = config.get('google_vision_api_key', '')
            key = value.strip() if isinstance(value, str) else ''
        except (OSError, ValueError, AttributeError):
            key = ''
    return key if key and key != PLACEHOLDER else ''


def read_optional_key(field, environment):
    value = os.environ.get(environment, '').strip()
    if value:
        return value
    try:
        value = json.loads((ROOT / 'config.local.json').read_text(encoding='utf-8-sig')).get(field, '')
        return value.strip() if isinstance(value, str) else ''
    except (OSError, ValueError, AttributeError):
        return ''


def public_link(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        return value if parsed.scheme in ('https', 'http') and parsed.hostname and not parsed.username and not parsed.password else None
    except ValueError:
        return None


def image_results(items):
    if not isinstance(items, list):
        return []
    result = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        url = public_link(item.get('url'))
        if url and url not in seen:
            seen.add(url)
            result.append({'url': url})
    return result


def normalize(web):
    if not isinstance(web, dict):
        raise HTTPException(502, 'Google returned an unexpected response. Please try again.')
    pages = []
    seen = set()
    for page in web.get('pagesWithMatchingImages', []):
        if not isinstance(page, dict):
            continue
        url = public_link(page.get('url'))
        if url and url not in seen:
            seen.add(url)
            pages.append({
                'url': url,
                'title': str(page.get('pageTitle') or urlsplit(url).hostname),
                'full_matches': image_results(page.get('fullMatchingImages')),
                'partial_matches': image_results(page.get('partialMatchingImages')),
            })
    return {
        'pages': pages,
        'full_matches': image_results(web.get('fullMatchingImages')),
        'partial_matches': image_results(web.get('partialMatchingImages')),
        'similar_images': image_results(web.get('visuallySimilarImages')),
        'web_entities': [str(e['description']) for e in web.get('webEntities', [])
                         if isinstance(e, dict) and isinstance(e.get('description'), str)],
        'labels': [str(e['label']) for e in web.get('bestGuessLabels', [])
                   if isinstance(e, dict) and isinstance(e.get('label'), str)],
    }


def prepare_image(content):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                if image.format not in ('JPEG', 'PNG') or getattr(image, 'n_frames', 1) != 1:
                    raise HTTPException(415, 'Please choose a single JPEG or PNG image.')
                if image.width * image.height > MAX_PIXELS:
                    raise HTTPException(413, 'Please use an image smaller than 20 megapixels.')
                image.load()
                analysis = ImageOps.exif_transpose(image).convert('RGB')
                analysis.thumbnail((1600, 1600))
                output = BytesIO()
                analysis.save(output, format='JPEG', quality=90)
                return output.getvalue(), analysis.size
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(415, 'This file cannot be read safely as a JPEG or PNG image.') from None


async def google_search(content, key):
    payload = {'requests': [{
        'image': {'content': base64.b64encode(content).decode('ascii')},
        'features': [{'type': 'WEB_DETECTION', 'maxResults': 20}, {'type': 'TEXT_DETECTION'}],
    }]}
    try:
        async with httpx.AsyncClient(timeout=35.0, follow_redirects=False) as client:
            response = await client.post(GOOGLE_ENDPOINT, headers={'X-Goog-Api-Key': key}, json=payload)
    except httpx.TimeoutException:
        raise HTTPException(504, 'Google did not respond in time. No automatic retry was made.') from None
    except httpx.RequestError:
        raise HTTPException(502, 'Could not connect to Google Vision. Check your internet connection.') from None
    messages = {
        400: 'Google rejected the request. Check the image and API key configuration.',
        401: 'Google rejected the API key. Check your Google Cloud credentials.',
        403: 'Google denied access. Check that Vision API and billing are enabled and the key permits Cloud Vision API.',
        429: 'Google quota has been reached. Check your Google Cloud quota and usage.',
    }
    if response.status_code == 403:
        try:
            reasons = {item.get('reason') for item in response.json().get('error', {}).get('details', []) if isinstance(item, dict)}
            if 'BILLING_DISABLED' in reasons:
                raise HTTPException(502, 'Google Cloud billing is disabled for the API key project. Link a billing account in Google Cloud Console, then retry.')
            if 'SERVICE_DISABLED' in reasons:
                raise HTTPException(502, 'Cloud Vision API is disabled for this project. Enable it in Google Cloud Console, then retry.')
        except (ValueError, TypeError, AttributeError):
            pass
    if response.status_code != 200:
        raise HTTPException(502, messages.get(response.status_code, 'Google Vision is unavailable. Please try again later.'))
    try:
        body = response.json()
        entry = body['responses'][0]
        if not isinstance(entry, dict):
            raise ValueError('Invalid response')
        if entry.get('error'):
            code = entry['error'].get('code')
            message = {7: messages[403], 8: messages[429], 16: messages[401]}.get(code, 'Google could not analyze this image. Try a different image.')
            raise HTTPException(502, message)
        # A successful empty annotation is a no-results outcome, not a fake result.
        return {**normalize(entry.get('webDetection', {})), 'clues': observations(entry)}
    except (ValueError, KeyError, IndexError, TypeError):
        raise HTTPException(502, 'Google returned an unexpected response. Please try again.') from None


@app.get('/')
def index():
    return FileResponse(ROOT / 'static' / 'index.html')


@app.get('/api/status')
def status():
    return {'stage': 5, 'configured': bool(read_key()), 'provider': 'Google Vision Web Detection',
            'implemented': ['search', 'evidence', 'visual_checks', 'extractive_context', 'report_export',
                            'evidence_scores', 'image_characteristics', 'scoped_watermark_checks']}


@app.post('/api/analyze-image')
async def inspect_image(request: Request, file: UploadFile = File(...)):
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Use the local application to analyze an image.')
    content = await file.read(MAX_BYTES + 1)
    await file.close()
    if len(content) > MAX_BYTES:
        raise HTTPException(413, 'Please choose a file smaller than 5 MB.')
    try:
        return await asyncio.to_thread(analyze_image, content)
    except (ValueError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(415, 'This file cannot be analyzed as a supported JPEG or PNG image.') from None


class EvidencePage(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    image_urls: list[str] = Field(default_factory=list, max_length=20)


class EvidenceInput(BaseModel):
    pages: list[EvidencePage] = Field(default_factory=list, max_length=5)
    case_id: str | None = Field(default=None, max_length=40)


@app.post('/api/evidence')
async def evidence(request: Request, payload: EvidenceInput):
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Open the application directly on its localhost address to collect evidence.')
    if evidence_lock.locked():
        raise HTTPException(429, 'Evidence collection is already running. Please wait for it to finish.')
    async with evidence_lock:
        if payload.case_id:
            expire_cases()
            case = cases.get(payload.case_id)
            if not case:
                raise HTTPException(404, 'This search expired. Run a new search to build its report.')
            pages = [{'url': page['url'], 'image_urls': [item['url'] for item in page['full_matches'] + page['partial_matches']][:20]}
                     for page in case['search']['pages'][:5]]
        else:
            case = None
            pages = [page.model_dump() for page in payload.pages]
        result = await collect_evidence(pages)
        report = build_report(result, case['verification'] if case else [], case['search'] if case else None)
        if case is not None:
            report['retrieval'] = retrieve_passages(result, case['search'].get('investigation', {}).get('clues', {}))
            report['investigation'] = case['search'].get('investigation')
        result['report'] = report
        if case is not None:
            case['report'] = report
            result.update(report=report, case_id=payload.case_id)
        return result


@app.get('/api/reports/{case_id}')
def export_report(case_id: str):
    expire_cases()
    case = cases.get(case_id)
    if not case or 'report' not in case:
        raise HTTPException(404, 'The report is unavailable or expired. Collect evidence after a new search.')
    return JSONResponse({'case_id': case_id, 'report': case['report'], 'verification': case['verification'],
                         'image_analysis': case.get('image_analysis'), 'text_integrity': case.get('text_integrity')},
        headers={'Content-Disposition': f'attachment; filename="pixelecho-report-{case_id[:8]}.json"'})


@app.post('/api/search')
async def search(request: Request, file: UploadFile = File(...)):
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Open the application directly on its localhost address to search.')
    key = read_key()
    if not key:
        raise HTTPException(503, 'Add your API key to config.local.json first. Follow the Google Vision connection steps in README.md.')
    content = await file.read(MAX_BYTES + 1)
    await file.close()
    if len(content) > MAX_BYTES:
        raise HTTPException(413, 'Please choose a file smaller than 5 MB.')
    if not content:
        raise HTTPException(400, 'Please select an image first.')
    image_bytes, dimensions = await asyncio.to_thread(prepare_image, content)
    if search_lock.locked():
        raise HTTPException(429, 'A search is already running. Please wait for it to finish.')
    start = time.monotonic()
    async with search_lock:
        image_analysis = await asyncio.to_thread(analyze_image, content)
        result = await google_search(image_bytes, key)
        clue = result.get('clues', {'text':'','words':[],'queries':[],'status':'unavailable'})
        requests = 1
        crop = crop_photo(image_bytes, clue)
        crop_info = {'status':'not_needed'}
        if crop:
            try:
                cropped = await google_search(crop[0], key)
                requests += 1
                for page in cropped['pages']:
                    page['retrieved_by'] = 'photo_crop'
                result['pages'].extend(cropped['pages'])
                for group in ('full_matches','partial_matches','similar_images'):
                    result[group].extend(cropped[group])
                crop_info = {'status':'searched','box':crop[1], 'note':'Heuristic text-band crop; not a detected object boundary.'}
            except HTTPException:
                requests += 1
                crop_info = {'status':'unavailable','note':'Crop search failed; full-image results retained.'}
        keyword_pages, keyword_status = await keyword_search(clue['queries'], read_optional_key('serper_api_key', 'SERPER_API_KEY'))
        result['pages'], related = rank_pages(result['pages'] + keyword_pages, clue)
        result['investigation'] = {'clues':clue, 'crop':crop_info, 'keyword_search':keyword_status, 'related_pages':related,
                                  'vision_requests':requests, 'note':'Visible text is unverified; graphic publisher and photograph creator may differ.'}
        verification = await verify_candidates(image_bytes, result)
        expire_cases()
        identifier = uuid4().hex
        initial_report = build_report({'pages': []}, verification, result)
        initial_report['investigation'] = result['investigation']
        cases[identifier] = {'created': time.monotonic(), 'search': result, 'verification': verification,
                             'report': initial_report, 'image_analysis': image_analysis, 'query_bytes': image_bytes}
        expire_cases()
    return {**result, 'elapsed_seconds': round(time.monotonic() - start, 2),
            'query_dimensions': list(dimensions), 'provider_requests': requests,
            'verification': verification, 'case_id': identifier, 'report': initial_report, 'image_analysis': image_analysis,
            'notice': 'Prototype visual checks and reported source claims are not proof of authenticity or creator identity.'}


class IntegrityInput(BaseModel):
    case_id: str = Field(min_length=1, max_length=40)


async def document_ocr(content, key):
    payload = {'requests':[{'image':{'content':base64.b64encode(content).decode('ascii')},
                            'features':[{'type':'DOCUMENT_TEXT_DETECTION'}]}]}
    async with httpx.AsyncClient(timeout=25, follow_redirects=False, trust_env=False) as client:
        response = await client.post(GOOGLE_ENDPOINT, headers={'X-Goog-Api-Key':key}, json=payload)
        response.raise_for_status()
        entry = response.json()['responses'][0]
        if entry.get('error'):
            raise ValueError('OCR unavailable')
        return paragraphs(entry)


@app.post('/api/text-integrity')
async def text_integrity(request: Request, payload: IntegrityInput):
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Use the local application to compare image text.')
    expire_cases()
    case = cases.get(payload.case_id)
    if not case:
        raise HTTPException(404, 'Search expired. Run a new search first.')
    if 'text_integrity' in case:
        return case['text_integrity']
    if search_lock.locked():
        raise HTTPException(429, 'An investigation is running. Please wait.')
    key = read_key()
    if not key:
        raise HTTPException(503, 'A Google Vision key is required for reference OCR.')
    async with search_lock:
        # Server-owned candidates only: clients cannot submit arbitrary fetch targets.
        urls = []
        for page in case['search'].get('pages', []):
            urls.extend(i['url'] for i in page.get('full_matches', []) + page.get('partial_matches', []))
        for group in ('full_matches','partial_matches'):
            urls.extend(i['url'] for i in case['search'].get(group, []))
        primary = list(dict.fromkeys(urls))
        similar = [i['url'] for i in case['search'].get('similar_images',[])]
        urls = list(dict.fromkeys(primary[:2] + similar[:2] + primary[2:] + similar[2:]))[:4]
        checks=[];ocr_requests=0;reference_ocr_count=0
        query = case.get('query_bytes')
        query_ocr = None
        for url in urls:
            stage = 'reference download'
            item = {'image_url':url, 'source_pages':[p['url'] for p in case['search'].get('pages',[]) if any(i['url']==url for i in p.get('full_matches',[])+p.get('partial_matches',[]))]}
            try:
                if not query:
                    raise ValueError('Query bytes unavailable')
                async with asyncio.timeout(90):
                    code,final,raw = await SafeFetcher().fetch(url,image=True)
                    if code!=200:
                        raise ValueError('Reference unavailable')
                    # decode() defines the alignment coordinate system and limits.
                    from visual import decode
                    stage = 'reference image decoding'
                    reference = await asyncio.to_thread(decode,raw)
                    ok,encoded = await asyncio.to_thread(cv2.imencode,'.png',reference)
                    if not ok:
                        raise ValueError('Reference decode failed')
                    ref_bytes = encoded.tobytes()
                    stage = 'geometric alignment'
                    geometry = await asyncio.to_thread(compare,query,ref_bytes,draw=False)
                    item['visual_status'] = geometry['status']
                    stage = 'scene difference analysis'
                    item['scene_comparison'] = await asyncio.to_thread(scene_differences,query,ref_bytes,geometry.get('alignment'))
                    if not geometry.get('alignment'):
                        item['comparison']={'status':'inconclusive','regions':[], 'reason':'No stable distributed image alignment.'}
                    elif reference_ocr_count >= 2:
                        item['comparison']={'status':'not_run','regions':[], 'reason':'Text OCR budget reached; visual comparison still ran.'}
                    else:
                        reference_ocr_count+=1
                        if query_ocr is None:
                            ocr_requests+=1
                            stage = 'uploaded image OCR'
                            query_ocr=await document_ocr(query,key)
                        ocr_requests+=1
                        stage = 'reference image OCR'
                        reference_ocr=await document_ocr(ref_bytes,key)
                        item['comparison']=await asyncio.to_thread(compare_text,query,ref_bytes,geometry['alignment'],query_ocr,reference_ocr)
                    item['final_url']=final
            except Exception:
                item['comparison']={'status':'unavailable','regions':[], 'reason':f'Could not complete {stage}. No negative authenticity conclusion follows.'}
            checks.append(item)
        result={'checks':checks,'upload_assessment':upload_assessment(checks), 'ocr_requests':ocr_requests,
                'budget':'At most four reference images, two reference OCR checks and three additional Google document OCR calls; repeats reuse this case result.',
                'notice':'Candidate references are not authenticated originals. Highlights indicate possible text or scene differences, not proof of forgery.'}
        case['text_integrity']=result
        return result
