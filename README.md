# PixelEcho

PixelEcho investigates image sources using Google Vision and selected 5Pils methods.
Text watermark checks and manual two-image comparison have been removed.


The five prototype stages are implemented: Google image search, webpage
evidence collection, conservative visual checks, extractive five-pillar
reporting, and local comparison/demo plus cited JSON export and printing.
Google searches require billing enabled on the API key's project.
There are no sample-result fallbacks. Provider results are not independent
visual verification or proof of the original source.

## Stages

1. **Implemented:** real image search from a basic local application.
2. **Implemented:** collect webpage evidence using selected 5Pils ideas.
3. **Implemented:** visual checks on up to four candidate images.
4. **Implemented:** extractive context fields with citations and unknowns.
5. **Implemented:** local comparison, demo fixtures, export, and printing.

## Interface

The interface adapts the supplied Meadow Rise design into the existing
buildless frontend: cream surfaces, green landscape layers, serif accents,
mist and gentle pointer parallax. The palette also covers search results,
evidence, score explanations, watermark checks and image measurements.
Local tools sit below the main investigation workspace and have working
navigation links. No React, Tailwind, Node build step or stock image is needed.

Motion follows the system reduced-motion preference and can also be paused
with the footer control. Keyboard focus, a skip link and small-screen layouts
are included. Print expands evidence/report details and restores their state
afterward. Existing uploads, APIs and JSON exports retain their behavior.

Redesign verification: 43 regression tests, inline JavaScript syntax, static
navigation/control checks, and FastAPI delivery of the page and stylesheet.
Browser visual inspection was not performed because Chrome access was denied.
Restart the server after this update so the new static asset route is loaded.

Local image measurements, embedded C2PA reading, and a narrow legacy watermark
check are also implemented. No OCR, LLM, database, or creator authentication is implemented.
See UPSTREAM.md for the sparse official 5Pils clone and pinned source.

## Evidence assessments and local media checks

Search reports include overall, source, evidence-item, and image-candidate
support scores. Each score exposes its weights and missing evidence.
Same-domain, shared-credit, duplicate-caption and near-duplicate article
sources are grouped to limit syndicated-copy inflation. The scores are
uncalibrated evidence assessments, not authenticity probabilities. Publisher
reliability remains explicitly unassessed; bylines do not become photo credits.

**Analyze image locally** works without Google or an API key. It measures
dimensions, color palette, brightness, contrast, sharpness proxy, edges,
entropy and transparency. It also reads embedded C2PA credentials offline
and checks the exact legacy StableDiffusionV1 dwtDct marker when supported.
Neither a copied watermark nor a detected manifest authenticates a creator.
C2PA presence, validation and signer trust are reported separately. Original
bytes are used for credentials; original stored pixels for the legacy marker.
No files or text are sent externally by these local endpoints.

The text panel measures text and explains unavailable/unsupported checks.
SynthID image detection is not integrated (an official manual detector link
is provided). SynthID Text detection is unavailable without the matching
generator configuration and tokenizer. No universal AI detector is claimed,
and non-detection never means human origin.

Endpoints: `POST /api/analyze-image` (JPEG/PNG multipart file, 5 MB/20 MP)
and `POST /api/check-text` (JSON text, 1–20,000 characters).
Search report exports include scores and image analysis. See
[method details and research](../docs/evidence-assessment-and-media-checks.md).

## Step 2 evidence collection

The default-on checkbox collects the first five page URLs from Google through
`POST /api/evidence`. It makes no additional Google API requests. Uncheck it
to run image search alone. Page requests send a research user agent to the
public websites; no image upload or Google key is forwarded to those sites.

Each result preserves the requested/final source URL, UTC retrieval time,
article text (up to 12,000 characters), page publication/modified dates,
and explicit image URL associations. A caption or credit is assigned only
when the supplied page-specific image URL is found in the page HTML.
Alt text stays separate from captions; article authors stay separate from
photographer credits. DOM association is not visual verification.

Unavailable, blocked, oversized, unsupported, and timed-out pages retain their
own status. Missing data remains unknown. The collector respects robots
policies and fails closed when the policy is unavailable. It fetches only
public HTTP/HTTPS addresses, pins the validated connection IP while preserving
TLS hostname verification, rechecks redirects, blocks environment proxies,
and applies 1 MB/per-page response limits and a 12-second page budget with
at most three concurrent pages. Data is kept only in the current response.

Page evidence feeds the extractive report below. Page dates are not asserted
as capture dates, and no authenticity verdict is generated.

## Visual verification and cited context

Up to four candidate images are downloaded through the guarded fetcher.
The prototype compares SIFT features, RANSAC alignment, feature spread,
overlap coverage, and aligned pixel error. Results are exact normalized pixels,
strong correspondence, inconclusive, or unavailable. Thresholds are uncalibrated
prototype choices, not identity/authenticity probabilities. Matching supports
only retained overlapping content; it does not prove every pixel is unchanged.

The report organizes prior use, reported source credit, reported image date,
location, and caption/event context. It uses associated captions and matching
ImageObject metadata. Unsupported fields remain unknown. Accepted visual
support yields a reported claim; unchecked claims remain candidates. Different
values are preserved without automatically inferring a contradiction. Page
publication observations remain separate from image/capture date claims.

The server issues a random case id and uses its own candidate/verification
records to construct the report, rather than trusting client-supplied match
claims. Up to eight cases are held in memory, with 15-minute expiry checked on
access. Restarting clears them; raw uploads are not retained. Download cited
JSON at /api/reports/{case_id}, or use the report print/save-as-PDF button.

## Demo now without Google billing

Open **Compare two local images** at the top of the application. Select
`demo/01-original.png` as the reference and `demo/02-cropped.png` as the
received image, then compare. Try `demo/03-compressed.jpg`,
`demo/04-simulated-canvas.png`, and `demo/05-unrelated.png` next.

These are synthetic fixtures generated by create_demo.py. The canvas is
simulated, not a genuine screenshot. You can also compare your own original
with a real screenshot or crop. This panel uses no Google API, does not search
the internet, and does not authenticate either image.

For the complete internet demo, enable Google billing, search a publicly
published image, leave evidence collection on, inspect visual checks and
context citations, then export the report. Failed live searches never fall
back to synthetic results.

## Start

From the project root in PowerShell:

```powershell
.\image-search\setup.ps1
.\image-search\start.ps1
```

Open http://127.0.0.1:8000. Keep the server terminal open. No activation is
needed. This is a local prototype, not a public deployment.

## Connect Google Vision

I can implement and test the application adapter. You must use your Google
account to create/select a Cloud project and enable billing. Do not send an
API key in chat.

1. Go to https://console.cloud.google.com/ and create/select a project.
2. Link billing to that project. Vision's free usage still requires billing.
3. Open APIs and Services > Library, find **Cloud Vision API**, and enable it.
4. Open APIs and Services > Credentials > Create credentials > API key.
5. Edit the key and restrict its API access to **Cloud Vision API**. This is
   a server-side call, so do not configure browser HTTP-referrer restrictions.
   If setting an IP restriction, use the backend's outgoing public IP.
6. Copy `config.example.json` to `config.local.json` in this folder and replace
   the placeholder locally with your key. Keep the key inside JSON quotes.
   The local config is excluded by .gitignore and is never returned to the UI.
7. Refresh the application. The status should say “API key configured”. This
   checks local configuration only; the first search verifies Google access.
8. Upload a known publicly available image and click **Search the web**.
   One click sends one WEB_DETECTION request; there is no automatic retry.

Alternatively set `GOOGLE_VISION_API_KEY` in the server process environment.
The environment takes precedence over the config file. No gcloud CLI is
needed for this API-key REST path. Never place the key in index.html.

## Expected results and errors

- Successful search: actual pages, full/partial matches, similar images,
  and web labels returned by Google. A valid response can have no matches.
- Key missing: the search button stays disabled; /api/search returns 503.
- Key invalid/API disabled/billing disabled: a readable Google access error.
- Timeout or quota reached: an explicit error with no fake replacement data.

The backend validates file signatures, caps input at 5 MB/20 megapixels,
normalizes orientation, and sends a JPEG analysis copy up to 1600 px per side.
Uploads are not saved. Animated images are rejected. Transparency is converted
to RGB for analysis, so use an opaque image when its background matters.

## Quota and checks

The published Web Detection allowance is 1,000 free units per month, then
USD 3.50 per 1,000 units at the standard rate (checked 13 November 2026).
This prototype has no application-level monthly spending cap. Keep an eye
on Cloud usage; budget alerts do not automatically stop charges.

```powershell
Set-Location .\image-search
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Automated checks use mocked Google responses and do not establish live
retrieval quality. A real image search remains to be verified after your key
is configured. Browser thumbnails load directly from provider-returned image
URLs; some hosts block them, while source links remain available.

Step 2 checks also cover extraction from fixture HTML, wrong-image caption
rejection, missing fields, date types, private/mixed DNS rejection, pinned
connections, private redirects, robots policies, response limits, and partial
results. A live collection probe of https://www.python.org/doc/ succeeded,
returning its page title and 420 characters of text on 13 November 2026.
The desktop/mobile evidence interface also passed a browser test with isolated
fixture responses, including collection requests, credit/date labels, expanded
text, and horizontal overflow checks. These fixtures are test-only and are not
part of the production API. The later-stage Python suite also checks visual
comparison, source/date separation, multiple credits, local comparison,
server-owned report cases, and export. These checks do not establish internet-
scale matching accuracy. The latest UI changes received a JavaScript syntax
check; browser inspection was unavailable because Chrome access was denied.

If a server was already running before these features were added, stop that server with
Ctrl+C and run `start.ps1` again, then refresh the browser. Changing only the
API key does not require a restart; adding new backend code does.

## Primary references

- https://docs.cloud.google.com/vision/docs/request
- https://docs.cloud.google.com/vision/docs/detecting-web
- https://cloud.google.com/vision/pricing
- https://github.com/UKPLab/5pils


## Clue-led retrieval upgrade

Search now requests Google TEXT_DETECTION alongside WEB_DETECTION. OCR text
and word boxes generate up to three observed-text queries; no MCC-specific
place names or guessed entities are injected. Separated top/bottom text bands
may produce one additional reverse-search crop. The crop is a heuristic,
not object detection. The original full image remains the visual reference.

Main results are reranked by text overlap and page-specific image availability.
Generic pages with neither are placed under lower-relevance leads. Ranking is
retrieval priority, not visual verification or publisher reliability. Cited
article passages are ranked using lexical overlap after evidence collection.
This is not embedding retrieval or an LLM implementation of full 5Pils.

To enable keyword web search, set SERPER_API_KEY in the server environment,
or add a nonempty serper_api_key field to config.local.json. Never put this
key in frontend JavaScript or share the local config. Missing keys and provider
failures remain explicit; OCR and image search still work without Serper.
The example config includes the field. Extracted text queries are sent to
Serper only when configured. No credential was added by this update.

Budget: up to two Vision HTTP requests per investigation (each includes Web
Detection and OCR, separately billable features), plus up to three Serper
queries. No automatic retry. Image-based and keyword-based retrieval are
merged by URL. Keyword-only pages without a matching image association remain
page-level leads; their text must not be presented as verified photo provenance.

Verified with 46 automated tests and JavaScript syntax/element checks. These
include OCR response parsing, query generation, crop coordinates, generic-page
demotion, missing-key behavior, and cited passage retrieval. Live OCR/search
quality on the user's image remains unverified. No paid live calls were made.

Remaining stages: learned embeddings and reranking, a configured multimodal
answer model, iterative source-link tracing, image extraction/verification on
keyword-only pages, and evaluation across a diverse labeled image set. These
are not represented as completed by this upgrade. Building recognition cannot
be inferred from dimensions, colors, OCR alone, or generic architecture labels.

References: https://docs.cloud.google.com/vision/docs/ocr and
https://serper.dev/; selected 5Pils provenance remains in UPSTREAM.md.


## SynthID access (13 November 2026)

The upload panel now has a prominent official manual SynthID Detector link
and instructions. This is an external manual workflow, not integrated detection.
No automatic upload, result import, or AI/human verdict is performed. The
analysis API continues to return SynthID unavailable with ran=false.

Google's official SynthID resources describe supported watermark checks:
https://deepmind.google/models/synthid/ and https://synthid.com/.
No usable public image-watermark detection endpoint was verified. Google's
separate AI Content Detection API requires private-preview access and describes
probabilistic artifact analysis; it must not be substituted or labeled SynthID:
https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/ai-content-detection

Automatic integration remains blocked on documented provider access and a
supported API contract. A generic Gemini vision response is not a watermark
measurement. Missing watermarks do not establish human origin.


## Uploaded-image text integrity and trust assessment

The default-on "Compare text" search option calls POST /api/text-integrity
with the server-owned case id after search. It safely fetches up to two full/
partial-match reference images (not arbitrary client URLs), aligns them using
SIFT/RANSAC, and sends the query plus aligned-candidate inputs to Google
DOCUMENT_TEXT_DETECTION. There are at most three additional OCR calls, cached
per case. Uncheck the option to avoid these extra requests. A repeated check
reuses the cached result. Raw query analysis bytes are retained only in bounded
in-memory cases (existing eight-case limit / 15-minute on-access expiry), never
written to disk or included in exports.

OCR paragraphs need confidence >=0.85, at least 20 normalized characters in
both compared text groups, and >=95% overlap in the compared region. Paragraphs
are projected into the query coordinate system and pooled into a fixed 3x5
spatial grid. This is a coarse layout heuristic: changed paragraph segmentation
or a shifted layout can produce false differences. Case and punctuation are
normalized. Unequal text with similarity <0.98 plus local mean pixel difference
>0.035 is flagged as a POSSIBLE text change; other uncertain comparisons remain
inconclusive. Text outside shared, readable regions is not assessed. No stable
alignment, poor OCR, absent references or provider errors produce no trust score.

The UI preserves both text readings, reference image/page links, OCR confidence
and a red-box preview of the uploaded image. This detects a difference between
versions, not which version is authentic. Even an older-looking reference is
not assumed original. Thresholds are prototype rules, not calibrated detectors.

The uploaded-image trust assessment is an explicitly uncalibrated consistency
index: geometric alignment 40; checked text agreement 40 (20 if mixed with
inconclusive checks); checked region coverage 4 per region, capped at 20. A
possible change caps the total at 35 and triggers "Review required". Repeated
copies do not add corroboration points. Only inconclusive checks yield a null
score. Agreement says "Consistent with checked references; authenticity
unproven", never "real" or "safe to trust". This is separate from the existing
source evidence score, watermark signals, and publisher reliability assessment.

JSON report exports now include text_integrity. Printing expands comparison
items. Tests cover same/changed text, uncertain OCR and geometry, actual fixture
alignment, server-owned candidates, failure handling, result caching, secret and
image-byte exclusion from exports, and no duplicate-copy score inflation.
56 tests pass. Latest UI JavaScript passes syntax and element-reference checks.
No live API calls or new browser visual inspection were performed. Performance
on the user's newspaper examples is not yet established. Remaining limits
include changed layouts, small or missing text, different OCR segmentation,
reference discovery beyond the two-candidate budget, and semantically equivalent
rewrites. Internet matches do not authenticate the newspaper or its content.

Comparison visibility fix: the upload text-integrity result now precedes the
search list. Per-reference diagnostics expose the failing pipeline stage and
OCR paragraph eligibility counts. Query planning prefers large OCR word boxes
over long tiny-print lines. These heuristics do not repair unreadable text or
guarantee correct matches; live newspaper comparison remains unverified.


## Visual scene differences (14 November 2026)

The image comparison now works without readable text. Four server-owned
reference URLs are considered, reserving slots for up to two similar-image
leads alongside full/partial matches. Similarity alone is never sufficient:
SIFT/RANSAC must establish distributed geometric alignment. Images with only
local resemblance or different viewpoints remain inconclusive.

Scene pixels are aligned, overlap-masked and border-eroded; mild blur and
robust global exposure correction suppress compression and lighting noise.
Residual changes use max(22, median+6*MAD) on a 0-255 scale. Small noise
components are removed. Broad changes (>35% overlap or median residual >25)
are inconclusive rather than treated as isolated manipulation. Localized
components become numbered boxes on the upload and aligned-reference preview.
The thresholds are hand-set and not benchmark-calibrated. Sparse subtle edits,
low-resolution faces, moving people, reflections, heavy compression, different
perspectives, and scene-wide changes may be missed or flagged incorrectly.

OpenCV's bundled frontal-face Haar cascade marks a changed region as a
face-area difference when it overlaps a detected face. This detector can miss
faces and does not recognize identity or establish a face swap. Other regions
are generic scene differences; no semantic object/environment model is loaded.
No biometric embeddings, name matching, or deepfake classifier is used.

The same API and cached export preserve scene_comparison independently of OCR:
OCR failure does not remove a completed visual result. The existing limit of
three extra OCR calls remains (two reference OCRs plus the query). Visual checks
use local CPU and add no detector API. The upload score can now be assessed
without text: alignment 30, agreement 30, overlapping coverage 20, additional
text evidence 20. Possible text/scene changes cap the score at 35; no-difference
results are capped at 80. No score establishes authenticity. Duplicate copies
add no points. C2PA and publisher reliability stay separate.

Regression checks include local replacement, face-area overlap labeling,
unchanged scenes, JPEG compression, global exposure, cropped overlap, missing
alignment, no-text scoring, duplicate suppression and similar-image retrieval.
The face-area test controls detector output; it does not benchmark real face
detection accuracy. The user's morphed-face image has not been tested against a
live retrieved original. Latest browser inspection remains unavailable; UI
JavaScript syntax and element references are checked separately.


## Compact results and source order

The hero tagline is smaller and centered. The step badge and visible palette
swatches were removed (palette statistics remain in machine-readable analysis,
but have no role in authenticity scoring). Results are separated into keyboard-
accessible Summary, Sources, Similar images, and Details tabs. Diagnostic data,
repeated region labels, source links and unavailable comparisons are collapsed;
changed-reference previews remain expanded. Local analysis opens Details.
Print displays all tab panels, including those hidden on screen.

The Sources tab sorts by oldest reported publication date after evidence
collection (at most five fetched pages). Unknown, future, invalid or conflicting
dates do not receive chronological priority. Modified dates are not publication
dates. Other discovered pages remain visible with unknown dates. The oldest
located page is not necessarily the original image upload, image capture date,
or a truthful source. A separate sort uses existing evidence-support scores.

Official-publisher ranking uses an exact-domain operator-maintained mapping:
add "official_sources": [{"domain": "your-verified-company-domain.example",
"label": "Verified company name"}] to config.local.json only after checking
that publisher identity. This example domain is a placeholder, not a verified
source. With no configured mapping, publisher identity is unverified; a famous
name, HTTPS or a matching logo does not certify a site. An official domain can
still contain edited or inaccurate material, and its connection to the uploaded
image is a separate question. No automated organization-ownership verification
or general publisher credibility model is claimed. Ranking metadata is included
in exported reports under report.source_ranking.

Validation includes source chronology, conflicting metadata, invalid/future
dates, exact-domain impersonation rejection, independent support-score labels,
static UI structure, JS syntax and dynamic tab/renderer smoke checks using a DOM
stub. Browser visual verification was not performed because prior Chrome access
was denied. Restart the backend for the ranking update, then refresh the page.


## Interactive architecture map

Open /architecture (or the Architecture link in the header) for a standalone
node graph of the current implementation: 17 components and 24 conceptual data
connections. Select nodes for input/output contracts, code references and
limitations. Drag nodes, pan empty canvas space, use zoom/Fit/Reset controls,
highlight Search/Compare/Local pipelines, or start the guided walkthrough.
Animations are illustrative, not live telemetry; the page performs no searches
or provider calls. Reduced-motion preferences and a pause control are supported.
The map does not imply a database, full 5Pils models, signed creation provenance,
identity recognition or automatic SynthID integration. It uses native HTML,
CSS, JavaScript and SVG with no framework/build dependencies. Page delivery,
asset responses, JS syntax and graph connectivity were checked. Browser visual
inspection remains unperformed because prior Chrome access was denied.


## Hosted deployment

Render-ready hostname and origin configuration is implemented. Use `python deploy.py`
as the hosted start command and `pip install -r requirements.lock.txt` to build.
See [DEPLOYMENT.md](DEPLOYMENT.md) for the complete settings, secret configuration,
state limitations and remaining cloud-validation steps. Nothing has been deployed
by this change. Local start.ps1 remains available.
