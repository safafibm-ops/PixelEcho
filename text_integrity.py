"""Spatial OCR comparison and explicitly uncalibrated upload evidence assessment."""
import base64
import re
from difflib import SequenceMatcher
import cv2
import numpy as np
from visual import decode

DISCLAIMER = ('Evidence consistency index, not a probability of authenticity. Internet copies can be wrong or edited. '
              'A difference does not establish which version is original; unchanged text does not establish truth.')

def normalize(text):
    return ' '.join(re.findall(r'[^\W_]+',text.casefold(),re.UNICODE))

def paragraphs(entry):
    result=[]
    for page in entry.get('fullTextAnnotation',{}).get('pages',[]):
        w,h=page.get('width',0),page.get('height',0)
        if not w or not h:continue
        for block in page.get('blocks',[]):
            for para in block.get('paragraphs',[]):
                text=' '.join(''.join(s.get('text','') for s in word.get('symbols',[])) for word in para.get('words',[]))
                vertices=para.get('boundingBox',{}).get('vertices',[])
                confidence=para.get('confidence')
                if vertices and isinstance(confidence,(int,float)):
                    result.append({'text':text[:2500],'confidence':float(confidence),
                        'polygon':[[v.get('x',0)/w,v.get('y',0)/h] for v in vertices]})
    return result[:200]

def bounds(points):
    return [float(points[:,0].min()),float(points[:,1].min()),float(points[:,0].max()),float(points[:,1].max())]

def buckets(items,size,transform=None):
    """Pool paragraphs into fixed spatial cells to tolerate line wrap differences."""
    groups={}
    for item in items:
        if item['confidence']<.85 or len(normalize(item['text']))<8:continue
        points=np.asarray(item['polygon'],np.float32)*np.asarray(size,np.float32)
        if transform is not None:points=cv2.perspectiveTransform(points[None],transform)[0]
        box=bounds(points);cx=(box[0]+box[2])/2;cy=(box[1]+box[3])/2
        groups.setdefault('items',[]).append({**item,'box':box,'center':[cx,cy]})
    return groups.get('items',[])

def compare_text(query_bytes,reference_bytes,alignment,query_ocr,reference_ocr):
    if not alignment:return {'status':'inconclusive','reason':'No distributed geometric alignment. Text is not compared between unrelated images.','regions':[]}
    q=decode(query_bytes);r=decode(reference_bytes);qh,qw=q.shape[:2]
    matrix=np.asarray(alignment['matrix'],float)
    ref=cv2.warpPerspective(r,matrix,(qw,qh))
    mask=cv2.warpPerspective(np.ones(r.shape[:2],np.uint8),matrix,(qw,qh))
    qs=buckets(query_ocr,[qw,qh]);rs=buckets(reference_ocr,[r.shape[1],r.shape[0]],matrix)
    regions=[]
    # Fixed cells compare pooled text, not unrelated OCR reading-order strings.
    for row in range(5):
        for col in range(3):
            x0,x1=col*qw/3,(col+1)*qw/3;y0,y1=row*qh/5,(row+1)*qh/5
            left=[i for i in qs if x0<=i['center'][0]<x1 and y0<=i['center'][1]<y1]
            right=[i for i in rs if x0<=i['center'][0]<x1 and y0<=i['center'][1]<y1]
            if not left or not right:continue
            left.sort(key=lambda i:(i['box'][1],i['box'][0]));right.sort(key=lambda i:(i['box'][1],i['box'][0]))
            a=' '.join(i['text'] for i in left);b=' '.join(i['text'] for i in right)
            if min(len(normalize(a)),len(normalize(b)))<20:continue
            combined=np.array([i['box'] for i in left+right]);box=[max(0,int(combined[:,0].min())),max(0,int(combined[:,1].min())),min(qw,int(combined[:,2].max())+1),min(qh,int(combined[:,3].max())+1)]
            x,y,xx,yy=box
            if xx<=x or yy<=y or mask[y:yy,x:xx].mean()<.95:continue
            similarity=SequenceMatcher(None,normalize(a),normalize(b)).ratio()
            error=float(np.abs(q[y:yy,x:xx].astype(float)-ref[y:yy,x:xx].astype(float)).mean()/255)
            state='agreement' if normalize(a)==normalize(b) else ('possible_text_change' if similarity<.98 and error>.035 else 'inconclusive')
            regions.append({'query_text':a,'reference_text':b,'box':box,'status':state,'text_similarity':round(similarity,3),
                            'pixel_difference':round(error,4),'minimum_ocr_confidence':min(i['confidence'] for i in left+right)})
    flagged=[i for i in regions if i['status']=='possible_text_change']
    for region in flagged:cv2.rectangle(q,tuple(region['box'][:2]),tuple(region['box'][2:]),(35,70,220),3)
    preview=None
    if flagged:
        ok,encoded=cv2.imencode('.jpg',q,[cv2.IMWRITE_JPEG_QUALITY,80])
        if ok:preview='data:image/jpeg;base64,'+base64.b64encode(encoded).decode()
    return {'status':'differences_found' if flagged else ('consistent_in_checked_regions' if regions and all(i['status']=='agreement' for i in regions) else 'inconclusive'),
            'regions':regions,'preview':preview,'coordinate_size':[qw,qh],
            'diagnostics':f'Query OCR: {len(query_ocr)} paragraphs, {len(qs)} eligible. Reference OCR: {len(reference_ocr)} paragraphs, {len(rs)} eligible. Comparable regions: {len(regions)}. Confidence threshold: 85%.',
            'reason':'Possible text differences require review: OCR errors, paragraph grouping and layout changes can cause mismatches. Only high-confidence, overlapping text regions are checked.'}

def text_assessment(checks):
    usable=[c for c in checks if any(r.get('status') in ('agreement','possible_text_change') for r in c.get('comparison',{}).get('regions',[]))]
    if not usable:return {'score':None,'verdict':'Insufficient evidence','factors':[], 'disclaimer':DISCLAIMER,
                          'reason':'No aligned reference with readable comparable text. Missing results do not establish authenticity.'}
    changed=any(c['comparison']['status']=='differences_found' for c in usable)
    uncertain=any(c['comparison']['status']=='inconclusive' for c in usable)
    # Best coverage, no bonus for repeated internet copies.
    checked=max(len(c['comparison']['regions']) for c in usable)
    coverage=min(20,checked*4)
    visual=40
    text=0 if changed else (20 if uncertain else 40)
    score=min(35,visual+text+coverage) if changed else visual+text+coverage
    return {'score':score,'verdict':'Review required — text differences found' if changed else ('Inconclusive — OCR differences need review' if uncertain else 'Consistent with checked references; authenticity unproven'),
            'reason':'No safe yes/no trust decision can be made from matching internet copies alone.',
            'factors':[{'name':'Geometrically aligned reference','points':visual,'maximum':40},
                       {'name':'Checked text agreement','points':text,'maximum':40},
                       {'name':'Comparable text-region coverage','points':coverage,'maximum':20}],
            'difference_cap':35 if changed else None,'disclaimer':DISCLAIMER,
            'scope':'Text consistency only; not an AI detector, source reliability rating, or verification of every image pixel.'}


def upload_assessment(checks):
    text=text_assessment(checks)
    scenes=[c['scene_comparison'] for c in checks if c.get('scene_comparison',{}).get('status') in ('differences_found','consistent_in_overlap')]
    if not scenes:return text
    changed=any(s['status']=='differences_found' for s in scenes) or any(c.get('comparison',{}).get('status')=='differences_found' for c in checks)
    uncertain=any(c.get('scene_comparison',{}).get('status')=='inconclusive' for c in checks)
    coverage=max(s['metrics']['overlap_fraction'] for s in scenes)
    agreement=0 if changed else 30
    visual=30
    overlap=round(coverage*20)
    text_points=0 if text['score'] is None or text.get('difference_cap') else min(20,round(text['score']/5))
    score=min(35,visual+agreement+overlap+text_points) if changed else min(80,visual+agreement+overlap+text_points)
    return {'score':score,'verdict':'Review required — visual or text differences found' if changed else 'No significant differences in checked overlap; authenticity unproven',
            'reason':'This is comparison with retrieved copies, not a determination that the uploaded image can be trusted. Unchecked content and reference origin remain unknown.',
            'factors':[{'name':'Geometric scene alignment','points':visual,'maximum':30},
                       {'name':'Visual/text agreement','points':agreement,'maximum':30},
                       {'name':'Best overlapping scene coverage','points':overlap,'maximum':20},
                       {'name':'Additional readable text evidence','points':text_points,'maximum':20}],
            'difference_cap':35 if changed else None,'disclaimer':DISCLAIMER,
            'scope':'Aligned visual and text consistency; no face identity recognition or automatic forgery verdict. No-difference scores are capped at 80.',
            'inconclusive_references_present':uncertain}
