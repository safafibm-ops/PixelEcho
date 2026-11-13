"""Reported chronology and explicit configured publisher identity, not truth ratings."""
from datetime import datetime, timezone
from urllib.parse import urlsplit


def rank_sources(search_pages, evidence, assessments, official_sources=None):
    by_url={p['requested_url'].split('#')[0]:p for p in evidence.get('pages',[])}
    scores={p['id']:p.get('score') for p in assessments.get('sources',[])}
    official_sources=official_sources if isinstance(official_sources,list) else []
    result=[]
    now=datetime.now(timezone.utc)
    for page in search_pages:
        found=by_url.get(page['url'].split('#')[0],{})
        dates=[]
        for date in found.get('page_dates',[]):
            if date.get('type')!='page_publication_date':continue
            try:
                parsed=datetime.fromisoformat(date['value'].replace('Z','+00:00'))
                if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=timezone.utc)
                if datetime(1990,1,1,tzinfo=timezone.utc)<=parsed<=now:
                    dates.append((parsed,date['value'],date.get('source')))
            except (ValueError,TypeError,KeyError):pass
        dates.sort(key=lambda d:d[0])
        # Different metadata values remain visible, never silently certified.
        distinct={d[0].date() for d in dates}
        date=dates[0] if dates and len(distinct)==1 else None
        host=urlsplit(found.get('final_url') or page['url']).hostname or ''
        origin=next((item for item in official_sources if isinstance(item,dict) and item.get('domain','').casefold()==host.casefold() and item.get('label')),None)
        result.append({**page,'publication_date':date[1] if date else None,
            'publication_date_source':date[2] if date else None,
            'date_status':'conflicting_metadata' if len(distinct)>1 else ('reported' if date else 'unknown'),
            'evidence_support_score':scores.get(found.get('id')),
            'publisher_origin':{'status':'configured_official_domain' if origin else 'unverified',
                'label':origin['label'] if origin else None,
                'note':'Exact domain is in the operator-maintained official publisher list; relevance to this image and truth are not established.' if origin else 'No verified publisher-domain mapping configured.'},
            'collection_status':found.get('status','not_collected'),
            '_sort_date':date[0].timestamp() if date else float('inf')})
    result.sort(key=lambda p:(p['_sort_date'],p['publisher_origin']['status']!='configured_official_domain',-(p['evidence_support_score'] or 0)))
    for page in result:page.pop('_sort_date')
    return {'pages':result,'order':'oldest_reported_first',
        'note':'Oldest located reported page date, not first upload or image capture date. Unknown/conflicting dates follow dated sources. Only collected pages can supply dates. Publisher identity and evidence support are separate from authenticity.'}
