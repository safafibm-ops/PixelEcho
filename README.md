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
