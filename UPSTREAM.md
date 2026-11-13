# Selected 5Pils source

Official repository: https://github.com/UKPLab/5pils

Pinned checkout: `acf672a20900f80e99f2d013aa2f30b7469fa180`.

A sparse clone is stored under `vendor/5pils`, including README, LICENSE,
notice, collection and answer-generation reference scripts, embedding code,
and page extraction helpers. The upstream code remains unchanged. It is
Apache-2.0; dataset annotations and linked images have separate terms.

Stage 1 adapts the WEB_DETECTION request concept from `detect_web` in
`scripts/collect_RIS_evidence.py`, using a new application adapter. It does
not execute the research pipeline or import its large model dependencies.
Stage 2 implements the collection workflow from `extract_info_trafilatura`
and `find_image_caption` in `dataset_collection/scrape_utils.py`. It uses
Trafilatura for article text and BeautifulSoup for explicitly associated
image captions and credits. It does not reuse the upstream fuzzy URL match,
generic following-sibling caption fallback, or unguarded network fetching.
The new collector pins validated public IPs, checks redirects and robots
policies, and bounds response size and collection time. The application now uses extractive question fields; upstream model-based
ranking and answer generation are not reproduced. No datasets or checkpoints are downloaded.

Recreate the selected checkout:

```powershell
git clone --filter=blob:none --sparse https://github.com/UKPLab/5pils.git vendor/5pils
git -C vendor/5pils checkout acf672a20900f80e99f2d013aa2f30b7469fa180
git -C vendor/5pils sparse-checkout set --no-cone /README.md /LICENSE /notice /scripts/collect_RIS_evidence.py /scripts/get_5pillars_answers.py /scripts/get_embeddings.py /dataset_collection/scrape_utils.py
```

## Local watermark reader

`vendor/legacy_watermark/maxDct.py` is the unmodified frequency-only class
from ShieldMnt/invisible-watermark 0.2.0, with its MIT license and source
hash recorded alongside it. The top-level upstream package imports the
neural RivaGAN stack even for this frequency method; this application uses
only the vendored class, NumPy, OpenCV and PyWavelets. It does not install
Torch or run RivaGAN. Production code only decodes the known legacy
StableDiffusionV1 marker; encoding is used solely in controlled tests.

C2PA reading uses the official `c2pa-python` package, pinned in the dependency
lock. It is independent of 5Pils. No signing key or trust root is installed
by the application. Tests generate an ephemeral untrusted certificate chain
in memory and never change application trust settings.
