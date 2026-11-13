"""Aligned scene difference localization. No identity recognition or AI-origin claim."""
import base64
import cv2
import numpy as np
from visual import decode


def face_boxes(image):
    detector=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    if detector.empty():return []
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    return [list(map(int,b)) for b in detector.detectMultiScale(gray,scaleFactor=1.1,minNeighbors=5,minSize=(24,24))]


def scene_differences(query_bytes,reference_bytes,alignment):
    base={'status':'inconclusive','regions':[],'preview':None,
          'note':'Differences can reflect editing, real scene movement, lighting or alignment errors. No person is identified; a changed face area does not prove a face swap or which image is original.'}
    if not alignment:return {**base,'reason':'No stable distributed geometric alignment; unrelated scenes are not compared.'}
    query=decode(query_bytes);reference=decode(reference_bytes);h,w=query.shape[:2]
    matrix=np.asarray(alignment['matrix'],float)
    aligned=cv2.warpPerspective(reference,matrix,(w,h))
    support=cv2.warpPerspective(np.ones(reference.shape[:2],np.uint8),matrix,(w,h))
    support=cv2.erode(support,np.ones((13,13),np.uint8)).astype(bool)
    support[:6]=False;support[-6:]=False;support[:,:6]=False;support[:,-6:]=False
    coverage=float(support.mean())
    if coverage<.35 or support.sum()<1500:return {**base,'reason':'Insufficient overlapping scene area to compare reliably.'}
    # Robust global exposure correction; local edits should remain local residuals.
    q=cv2.GaussianBlur(query,(5,5),1.2).astype(np.float32)
    r=cv2.GaussianBlur(aligned,(5,5),1.2).astype(np.float32)
    corrected=r.copy()
    for channel in range(3):
        qa=q[:,:,channel][support];ra=r[:,:,channel][support]
        qlo,qhi=np.percentile(qa,[20,80]);rlo,rhi=np.percentile(ra,[20,80])
        gain=float(np.clip((qhi-qlo)/max(1,rhi-rlo),.7,1.4)) if rhi-rlo>10 else 1
        offset=float(np.median(qa-gain*ra))
        corrected[:,:,channel]=np.clip(gain*r[:,:,channel]+offset,0,255)
    error=np.mean(np.abs(q-corrected),axis=2)
    median=float(np.median(error[support]));mad=float(np.median(np.abs(error[support]-median)))
    threshold=max(22.,median+6*max(1.,mad))
    changed=((error>threshold)&support).astype(np.uint8)*255
    changed=cv2.morphologyEx(changed,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    changed=cv2.morphologyEx(changed,cv2.MORPH_CLOSE,np.ones((7,7),np.uint8))
    changed[~support]=0
    fraction=float((changed[support]>0).mean())
    metrics={'overlap_fraction':round(coverage,3),'changed_overlap_fraction':round(fraction,4),
             'median_residual_0_255':round(median,2),'threshold_0_255':round(threshold,2)}
    if fraction>.35 or median>25:
        return {**base,'metrics':metrics,'reason':'Broad scene differences or unstable registration. Cannot isolate an edit reliably.'}
    faces=face_boxes(query)+face_boxes(aligned)
    contours,_=cv2.findContours(changed,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    regions=[]
    for contour in sorted(contours,key=cv2.contourArea,reverse=True):
        x,y,bw,bh=cv2.boundingRect(contour)
        if cv2.contourArea(contour)<max(60,w*h*.0006) or min(bw,bh)<9:continue
        density=float((changed[y:y+bh,x:x+bw]>0).mean())
        if density<.12:continue
        hits=[]
        for fx,fy,fw,fh in faces:
            intersection=max(0,min(x+bw,fx+fw)-max(x,fx))*max(0,min(y+bh,fy+fh)-max(y,fy))
            if intersection/max(1,fw*fh)>.15:hits.append([fx,fy,fw,fh])
        regions.append({'box':[x,y,x+bw,y+bh], 'kind':'face_area_difference' if hits else 'scene_region_difference',
                        'changed_pixel_fraction':round(density,3), 'face_detection_overlap':bool(hits)})
        if len(regions)>=12:break
    if not regions and fraction>.025:return {**base,'metrics':metrics,'reason':'Scattered residual differences; no reliable localized region.'}
    left=query.copy();right=aligned.copy()
    for i,region in enumerate(regions):
        x,y,xx,yy=region['box']
        for image in (left,right):
            cv2.rectangle(image,(x,y),(xx,yy),(30,60,230),2)
            cv2.putText(image,str(i+1),(x,max(15,y-4)),cv2.FONT_HERSHEY_SIMPLEX,.55,(30,60,230),2)
    cv2.putText(left,'UPLOAD',(12,25),cv2.FONT_HERSHEY_SIMPLEX,.65,(30,60,230),2)
    cv2.putText(right,'ALIGNED REFERENCE',(12,25),cv2.FONT_HERSHEY_SIMPLEX,.65,(30,60,230),2)
    preview=np.concatenate([left,right],axis=1)
    scale=min(1,1400/preview.shape[1]);preview=cv2.resize(preview,None,fx=scale,fy=scale)
    ok,encoded=cv2.imencode('.jpg',preview,[cv2.IMWRITE_JPEG_QUALITY,82])
    return {**base,'status':'differences_found' if regions else 'consistent_in_overlap','regions':regions,'metrics':metrics,
            'coordinate_size':[w,h],'face_detector':'OpenCV frontal-face Haar cascade; may miss faces, no recognition',
            'preview':'data:image/jpeg;base64,'+base64.b64encode(encoded).decode() if ok else None,
            'reason':'Localized visual changes found; compare the numbered regions.' if regions else 'No significant localized difference found in the overlapping scene under these prototype thresholds.'}
