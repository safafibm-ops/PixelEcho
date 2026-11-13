"""Extractive five-pillar reporting. No LLM, guessed identities, or inferred motives."""
from datetime import datetime, timezone
import re

from visual import ACCEPTED


def context_report(collected, verifications):
    checked = {item['image_url']: item for item in verifications}
    claims = {key: [] for key in ('source', 'date', 'location', 'context')}
    occurrences = []
    timeline = []
    sources = []
    for page in collected.get('pages', []):
        if page.get('status') != 'collected':
            continue
        reference = {'evidence_id': page['id'], 'url': page.get('final_url') or page['requested_url'], 'title': page.get('title')}
        sources.append(reference)
        page_supported = False
        for association in page.get('image_associations', []):
            if association['association'] != 'image_element_located':
                continue
            image_url = association['image_url']
            status = checked.get(image_url, {}).get('status', 'not_checked')
            supported = status in ACCEPTED
            page_supported = page_supported or supported
            caption = association.get('caption')
            def add(field, value, kind, quote):
                if value:
                    claims[field].append({'value': value, 'kind': kind, 'quote': quote,
                        'evidence_id': page['id'], 'url': reference['url'], 'image_url': image_url,
                        'visual_status': status})
            credit = association.get('reported_credit')
            add('source', credit, 'reported_image_credit', credit)
            add('context', caption, 'associated_caption', caption)
            if caption:
                place = re.search(r'\bLocation\s*:\s*([^|;]+)', caption, re.I)
                if place:
                    add('location', place.group(1).strip(), 'explicit_caption_location', caption)
                date = re.search(r'\b(?:taken|captured|photographed)(?:\s+on)?\s*:?\s*(\d{4}-\d{2}-\d{2})\b', caption, re.I)
                if date:
                    try:
                        datetime.fromisoformat(date.group(1))
                        add('date', date.group(1), 'reported_capture_date', caption)
                    except ValueError:
                        pass
            for metadata in page.get('image_metadata', []):
                if metadata['image_url'] != image_url:
                    continue
                add('source', metadata.get('creator'), 'image_object_creator', metadata.get('creator'))
                add('location', metadata.get('location'), 'image_object_content_location', metadata.get('location'))
                # dateCreated is an asset creation claim, not necessarily capture.
                add('date', metadata.get('date_created'), 'reported_image_creation_date', metadata.get('date_created'))
                if not caption:
                    add('context', metadata.get('caption'), 'image_object_caption', metadata.get('caption'))
        occurrences.append({**reference, 'visual_support': 'supported' if page_supported else 'unverified'})
        for date in page.get('page_dates', []):
            if date['type'] == 'page_publication_date':
                timeline.append({**reference, 'value': date['value'], 'type': date['type'],
                                 'date_source': date['source'], 'visual_support': 'supported' if page_supported else 'unverified'})

    fields = {}
    for field, values in claims.items():
        supported = [claim for claim in values if claim['visual_status'] in ACCEPTED]
        selected = supported or values
        def normalized_value(claim):
            value = claim['value'].casefold().strip()
            if field == 'source':
                value = re.sub(r'^(?:photo(?:graph)?(?: credit)?|image credit|credit)\s*[:©]\s*', '', value)
            return value
        different = {normalized_value(claim) for claim in selected}
        status = 'unknown' if not selected else ('multiple_reports' if len(different) > 1 else ('reported' if supported else 'candidate'))
        fields[field] = {'status': status, 'claims': selected, 'value': selected[0]['value'] if len(different) == 1 else None}
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'prior_use': {'status': 'observed' if any(item['visual_support'] == 'supported' for item in occurrences) else ('candidate' if occurrences else 'unknown'),
                      'occurrences': occurrences},
        'fields': fields, 'publication_observations': timeline, 'sources': sources,
        'limitations': [
            'No creator identity or first uploader is authenticated.',
            'Page publication dates are not capture dates or proof of when an image was added.',
            'A reported image creation date is not necessarily a camera capture date.',
            'Context is quoted caption evidence; private motivation is not inferred.',
            'Different reported values are preserved; a semantic contradiction is not automatically inferred.',
            'Visual matching uses uncalibrated prototype checks and supports only retained overlapping content.',
            'Missing evidence does not mean an image is fake or AI generated.',
        ],
    }
