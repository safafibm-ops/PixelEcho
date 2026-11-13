"""Transparent evidence-support scores, never probabilities of authentic origin."""
import hashlib
import re
from urllib.parse import urlsplit

from tld import get_fld
from visual import ACCEPTED

SOURCE_WEIGHTS = {'visual_correspondence': 40, 'image_association': 15,
                  'attribution': 15, 'image_context': 15, 'traceability': 15}
ITEM_WEIGHTS = {'visual_correspondence': 40, 'image_association': 20,
                'traceability': 20, 'explicit_support': 20}
DISCLAIMER = ('An uncalibrated assessment of available evidence, not the probability that an image '
              'is authentic, human-made, or credited to the right creator. Publisher reliability is not rated.')


def norm(value):
    return re.sub(r'\W+', ' ', str(value or '').casefold()).strip()


def credit_key(value):
    return norm(re.sub(r'^(?:photo(?:graph)?(?: credit)?|image credit|credit)\s*[:©]\s*', '', str(value or ''), flags=re.I))


def factor(name, points, weight, reason):
    return {'name': name, 'points': points, 'weight': weight, 'reason': reason}


def source_assessment(page, checked):
    identifier = page.get('id') or hashlib.sha256(page['requested_url'].encode()).hexdigest()[:12]
    associated = [a for a in page.get('image_associations', []) if a.get('association') == 'image_element_located']
    statuses = [checked.get(a['image_url'], {}).get('status') for a in associated]
    visual = 40 if 'exact_pixels' in statuses else (32 if 'strong_correspondence' in statuses else 0)
    available = page.get('status') == 'collected'
    metadata = [m for m in page.get('image_metadata', []) if any(a['image_url'] == m['image_url'] for a in associated)]
    credited = any(a.get('reported_credit') for a in associated) or any(m.get('creator') for m in metadata)
    captions = [a.get('caption') for a in associated if a.get('caption')]
    dated = any(m.get('date_created') for m in metadata) or any(re.search(r'\b(?:taken|captured|photographed)(?:\s+on)?\s*:?\s*\d{4}-\d{2}-\d{2}', c, re.I) for c in captions)
    located = any(m.get('location') for m in metadata) or any(re.search(r'\bLocation\s*:', c, re.I) for c in captions)
    context_points = (3 if captions else 0) + (6 if dated else 0) + (6 if located else 0)
    trace = sum([5 if page.get('requested_url') else 0, 5 if page.get('retrieved_at') else 0, 5 if page.get('id') else 0]) if available else 0
    factors = [
        factor('visual_correspondence', visual, 40, 'Exact normalized pixels: 40; strong prototype match: 32; otherwise: 0. Only page-associated images count.'),
        factor('image_association', 15 if associated else 0, 15, '15 if an exact Google-reported image URL is located in page HTML; this is not pixel verification.'),
        factor('attribution', 15 if credited else 0, 15, '15 for an explicit associated image credit or ImageObject creator; article bylines do not count.'),
        factor('image_context', context_points, 15, 'Associated caption: 3; explicit image date: 6; explicit location: 6. Page dates do not count as image dates.'),
        factor('traceability', trace, 15, 'Five points each for a collected source URL, retrieval timestamp, and evidence id. This measures auditability, not truth.'),
    ]
    missing = [f['name'] for f in factors if f['points'] == 0]
    missing.extend(name for name, present in [('associated_caption', captions), ('explicit_image_date', dated),
                                            ('explicit_image_location', located)] if not present)
    return {'id': identifier, 'url': page.get('final_url') or page['requested_url'],
            'title': page.get('title'), 'status': 'assessed' if available else page.get('status', 'not_collected'),
            'score': sum(f['points'] for f in factors) if available else None,
            'factors': factors, 'missing_evidence': missing,
            'visual_support': visual > 0,
            'source_reliability': {'score': None, 'status': 'not_assessed',
                'reason': 'No publisher reputation, independent editorial review, or publisher identity verification is configured. No reliability points are awarded.'}}


def evidence_items(page, source):
    if page.get('status') != 'collected':
        return []
    items = []
    def add(kind, text, image_url=None, scope='page'):
        if not text:
            return
        visual = next(f['points'] for f in source['factors'] if f['name'] == 'visual_correspondence')
        association = 20 if scope == 'image' else (10 if any(a.get('association') == 'image_element_located' for a in page.get('image_associations', [])) else 0)
        explicit = 20 if kind in ('image_credit', 'image_caption', 'image_object_creator', 'image_object_location', 'image_object_date') else (15 if kind.startswith('page_') and kind.endswith('_date') else (10 if kind in ('image_alt_text', 'article_author') else 5))
        if image_url:
            status = page.get('_checked', {}).get(image_url, {}).get('status')
            visual = 40 if status == 'exact_pixels' else (32 if status == 'strong_correspondence' else 0)
        factors = [factor('visual_correspondence', visual, 40, 'The linked image has accepted prototype correspondence, or contributes no visual points.'),
                   factor('image_association', association, 20, 'Image-scoped quotation: 20; page-scoped material with a located image: 10; otherwise: 0.'),
                   factor('traceability', 20, 20, 'The item has a source URL, evidence id, and retained quotation.'),
                   factor('explicit_support', explicit, 20, 'Explicit image statement: 20; page date: 15; byline/alt text: 10; general page text: 5. These are not truth ratings.')]
        items.append({'id': f'{source["id"]}:{len(items)+1}', 'source_id': source['id'], 'kind': kind,
                      'scope': scope, 'image_url': image_url, 'quote': str(text)[:800], 'url': source['url'],
                      'score': sum(f['points'] for f in factors), 'factors': factors,
                      'limitation': 'Page-scoped material is not asserted to describe the photograph.' if scope == 'page' else 'Reported image-associated statement; creator identity is not authenticated.'})
    for association in page.get('image_associations', [])[:20]:
        if association.get('association') != 'image_element_located':
            continue
        for key, kind in [('caption', 'image_caption'), ('reported_credit', 'image_credit'), ('alt_text', 'image_alt_text')]:
            add(kind, association.get(key), association['image_url'], 'image')
    for metadata in page.get('image_metadata', [])[:20]:
        if not any(a.get('association') == 'image_element_located' and a['image_url'] == metadata['image_url'] for a in page.get('image_associations', [])):
            continue
        for key, kind in [('creator', 'image_object_creator'), ('location', 'image_object_location'), ('date_created', 'image_object_date')]:
            add(kind, metadata.get(key), metadata['image_url'], 'image')
    for date in page.get('page_dates', [])[:20]:
        add(date['type'], date['value'])
    add('article_author', page.get('article_author'))
    add('page_text', page.get('text'))
    return items


def publisher(url):
    try:
        return get_fld(url, fail_silently=True) or urlsplit(url).hostname or ''
    except ValueError:
        return ''


def shingles(text):
    words = norm(text).split()
    return {' '.join(words[i:i+5]) for i in range(max(0, len(words)-4))}


def group_sources(pages, sources):
    parents = list(range(len(pages)))
    reasons = []
    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index
    for i, left in enumerate(pages):
        for j in range(i):
            right = pages[j]
            reason = None
            if publisher(sources[i]['url']) == publisher(sources[j]['url']):
                reason = 'same publisher domain'
            credits_left = {credit_key(a.get('reported_credit')) for a in left.get('image_associations', []) if a.get('reported_credit')}
            credits_right = {credit_key(a.get('reported_credit')) for a in right.get('image_associations', []) if a.get('reported_credit')}
            if credits_left & credits_right:
                reason = 'same credited image origin'
            ls, rs = shingles(left.get('text', '')), shingles(right.get('text', ''))
            if min(len(ls), len(rs)) >= 15 and len(ls & rs) / max(1, len(ls | rs)) >= .8:
                reason = 'substantially duplicated article text'
            lc = {norm(a.get('caption')) for a in left.get('image_associations', []) if len(norm(a.get('caption'))) >= 40}
            rc = {norm(a.get('caption')) for a in right.get('image_associations', []) if len(norm(a.get('caption'))) >= 40}
            if lc & rc:
                reason = 'duplicated associated caption'
            if reason:
                parents[root(i)] = root(j)
                reasons.append({'source_ids': [sources[i]['id'], sources[j]['id']], 'reason': reason})
    groups = {}
    for index, source in enumerate(sources):
        groups.setdefault(root(index), []).append(source['id'])
    result = [{'id': f'group-{i+1}', 'source_ids': ids} for i, ids in enumerate(groups.values())]
    return result, reasons


def assess(collected, checks, report, image_candidates=None):
    checked = {item['image_url']: item for item in checks}
    pages = collected.get('pages', [])
    sources = [source_assessment(page, checked) for page in pages]
    items = [item for page, source in zip(pages, sources) for item in evidence_items({**page, '_checked': checked}, source)]
    groups, grouping_reasons = group_sources(pages, sources)
    groups_by_source = {identifier: group['id'] for group in groups for identifier in group['source_ids']}
    shared_claim_groups = {}
    unresolved = []
    for field in ('source', 'date', 'location'):
        claims = report.get('fields', {}).get(field, {}).get('claims', [])
        kinds = {}
        for claim in claims:
            if claim.get('visual_status') not in ACCEPTED:
                continue
            value = credit_key(claim['value']) if field == 'source' else norm(claim['value'])
            kinds.setdefault(claim['kind'], set()).add(value)
            group = groups_by_source.get(claim['evidence_id'])
            if group:
                shared_claim_groups.setdefault((field, claim['kind'], value), set()).add(group)
        if any(len(values) > 1 for values in kinds.values()):
            unresolved.append(field)
    supported = [source for source in sources if source['score'] is not None and source['visual_support']]
    independent_support = max((len(ids) for ids in shared_claim_groups.values()), default=0)
    bonus = min(15, max(0, independent_support - 1) * 5)
    penalty = min(15, len(unresolved) * 5)
    best = max((source['score'] for source in supported), default=0)
    score = max(0, round(.85 * best + bonus - penalty)) if supported else None
    for source in sources:
        source['corroboration_group'] = groups_by_source[source['id']]
    visual_items = []
    for image_url in dict.fromkeys([item['image_url'] for item in checks] + list(image_candidates or [])):
        check = checked.get(image_url, {})
        status = check.get('status', 'not_checked')
        visual_items.append({'image_url': image_url, 'status': status,
            'score': {'exact_pixels': 100, 'strong_correspondence': 80, 'inconclusive': 0}.get(status),
            'factor': 'Exact normalized pixels: 100; accepted prototype correspondence: 80; inconclusive: 0; unavailable/unchecked: no score.',
            'note': 'Visual support index only, not origin or authenticity probability. Candidate checks are limited to four images.'})
    return {'policy': 'evidence_support_v1', 'label': 'Evidence trust assessment', 'disclaimer': DISCLAIMER,
            'overall': {'score': score, 'status': 'assessed' if supported else 'insufficient_evidence',
                'formula': '0.85 × best visually supported source score + independent agreement bonus − unresolved-difference penalty',
                'best_source_score': best if supported else None, 'independent_agreement_bonus': bonus,
                'unresolved_difference_penalty': penalty, 'unresolved_fields': unresolved,
                'missing': [] if supported else ['No collected source has an accepted visual match to the upload.'],
                'note': 'Bonus: 5 per additional group agreeing on an explicit claim, maximum 15. Difference penalty: 5 per field with differing same-kind supported values, maximum 15; this flags unresolved differences, not proven contradictions.'},
            'sources': sources, 'evidence_items': items, 'visual_items': visual_items, 'source_weights': SOURCE_WEIGHTS, 'item_weights': ITEM_WEIGHTS,
            'corroboration_groups': groups, 'grouping_reasons': grouping_reasons,
            'independence_note': 'Same-domain, shared-credit, duplicate-caption, or near-duplicate article sources are grouped. Different groups are only potentially independent; independence is not proven.',
            'source_reliability': {'status': 'not_assessed', 'score': None, 'weight': 0,
                'reason': 'No external reputation or editorial reliability assessment is configured. HTTPS, a byline, and a high evidence score do not establish publisher credibility.'}}
