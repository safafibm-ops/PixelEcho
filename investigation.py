"""Bounded clue-led retrieval; observations are not verified scene identities."""
from io import BytesIO
import re
from urllib.parse import urlsplit
import httpx
from PIL import Image

STOP = set('the and for with this that from image photo news removal orders into about what how building commercial'.split())

def words(text):
    return [w for w in re.findall(r'[^\W_]+', text.casefold(), re.UNICODE) if len(w)>2 and w not in STOP]

def observations(entry):
    annotations = entry.get('textAnnotations') or []
    text = str(entry.get('fullTextAnnotation', {}).get('text') or (annotations[0].get('description', '') if annotations else ''))[:12000]
    boxes=[]
    for item in annotations[1:501]:
        vertices=item.get('boundingPoly',{}).get('vertices',[])
        if vertices:
            boxes.append({'text':str(item.get('description',''))[:200], 'vertices':[{'x':int(v.get('x',0)), 'y':int(v.get('y',0))} for v in vertices[:4]]})
    lines=[' '.join(line.split()) for line in text.splitlines() if len(words(line))>=2]
    # Preserve observed phrases; never inject a guessed location or publisher.
    lines=sorted(dict.fromkeys(lines),key=lambda line:len(words(line)),reverse=True)
    queries=[]
    for line in lines[:3]:
        phrase=' '.join(line.split()[:16])[:180]
        queries.append(phrase)
    if len(lines)>1:
        queries.insert(0, ' '.join(lines[-1].split()[:5])+' '+ ' '.join(lines[0].split()[:12]))
    queries=list(dict.fromkeys(queries))[:3]
    return {'text':text,'words':boxes,'queries':queries,'status':'detected' if text else 'not_detected',
            'note':'OCR transcribes visible claims and branding; it does not verify the building, publisher or event.'}

def crop_photo(content, clue):
    """Remove separated top/bottom text bands only; retain original for all checks."""
    with Image.open(BytesIO(content)) as im:
        w,h=im.size
        top=[v['y'] for item in clue['words'] for v in item['vertices'] if all(p['y']<h*.17 for p in item['vertices'])]
        bottom=[v['y'] for item in clue['words'] for v in item['vertices'] if all(p['y']>h*.72 for p in item['vertices'])]
        y0=min(int(h*.17),max(top,default=0)+4) if top else 0
        y1=max(int(h*.72),min(bottom)-4) if bottom else h
        if y0==0 and y1==h or y1-y0<h*.55:return None
        out=BytesIO();im.convert('RGB').crop((0,y0,w,y1)).save(out,'JPEG',quality=92)
        return out.getvalue(), [0,y0,w,y1]

async def keyword_search(queries,key):
    if not queries:return [],{'status':'not_run','requests':0,'reason':'No usable OCR queries were extracted; no keyword request sent.'}
    if not key:return [],{'status':'unavailable','requests':0,'reason':'Configure SERPER_API_KEY or serper_api_key for keyword web search. Generated queries remain visible.'}
    pages=[];errors=0
    async with httpx.AsyncClient(timeout=15,follow_redirects=False,trust_env=False) as client:
        for query in queries[:3]:
            try:
                response=await client.post('https://google.serper.dev/search',headers={'X-API-KEY':key},json={'q':query,'num':6})
                response.raise_for_status()
                for item in response.json().get('organic',[])[:6]:
                    link=item.get('link','');parsed=urlsplit(link)
                    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:continue
                    pages.append({'url':link,'title':str(item.get('title',''))[:500], 'snippet':str(item.get('snippet',''))[:1000],
                                  'full_matches':[],'partial_matches':[],'retrieved_by':'keyword','query':query})
            except (httpx.HTTPError,ValueError,TypeError):errors+=1
    return pages,{'status':'partial' if errors and pages else ('unavailable' if errors else 'completed'), 'requests':len(queries[:3]), 'reason':'Some keyword searches failed; no substituted results.' if errors else 'Bounded keyword search completed.'}

def rank_pages(pages,clue):
    tokens=set(words(clue['text'])); merged={}
    for page in pages:
        key=page['url'].split('#')[0]
        if key in merged:
            for group in ('full_matches','partial_matches'):
                merged[key][group]+=page.get(group,[])
            continue
        merged[key]={**page}
    ranked=[];related=[]
    for page in merged.values():
        overlap=sorted(tokens & set(words(page.get('title','')+' '+page.get('snippet','')+' '+page['url'])))
        associated=bool(page.get('full_matches') or page.get('partial_matches'))
        page.update(relevance={'matching_terms':overlap,'image_candidate_available':associated,
                               'score':min(100,len(overlap)*12+(35 if associated else 0)),
                               'note':'Retrieval priority only; not source authenticity or visual verification.'})
        (ranked if associated or len(overlap)>=2 or not tokens else related).append(page)
    ranked.sort(key=lambda p:p['relevance']['score'],reverse=True)
    return ranked[:25],related[:20]

def retrieve_passages(collected,clue):
    """Lexical baseline, explicitly not learned embeddings or generated answers."""
    tokens=set(words(clue.get('text','')));passages=[]
    for page in collected.get('pages',[]):
        if page.get('status')!='collected':continue
        text=page.get('text','')
        for offset in range(0,len(text),600):
            quote=text[offset:offset+900];overlap=sorted(tokens & set(words(quote)))
            if len(overlap)>=2:
                passages.append({'evidence_id':page['id'],'url':page.get('final_url') or page['requested_url'],
                                 'quote':quote,'matching_terms':overlap,'score':len(overlap),
                                 'scope':'page_text_not_verified_image_context'})
    return {'method':'lexical_overlap_baseline','passages':sorted(passages,key=lambda p:p['score'],reverse=True)[:8],
            'embedding_status':'not_configured','multimodal_answer_status':'not_configured',
            'note':'Quoted passages are investigation leads. No semantic embedding model or multimodal answer model ran.'}
