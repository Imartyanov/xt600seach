"""Verify plausible listing photos with Gemini Vision and cache by image hashes."""
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')
THRESHOLD = float(os.environ.get('VISION_CONFIDENCE_THRESHOLD', '0.85'))
MAX_CHECKS = int(os.environ.get('VISION_MAX_CHECKS', '20'))
PROMPT = """Inspect only the attached photos from one Kleinanzeigen listing. Return JSON only:
{"is_xt600z_3aj": boolean, "is_red_white": boolean, "is_complete_motorcycle": boolean, "confidence": number, "reason": string}
Visually determine whether this is a Yamaha XT600Z Tenere generation 3AJ, red-white, and a complete motorcycle. Seller text is not evidence. If uncertain, lower confidence."""

def plausible(row):
    title = row.get('title', '')
    if re.search(r'(?i)\b(suche|gesuch|teile|ersatzteil|tank|motor|rahmen|sitzbank|verkleidung|gabel|felge|e[ -]?scooter|xt\s*1200|xtz\s*700|tt\s*600|dr\s*600|3tb|3uw|2kf|43f|34l|1vj)\b', title):
        return False
    return bool(re.search(r'(?i)(3\s*aj|ten[eé]r[eé]|xt\s*600\s*z)', title))

def extract_photos(page, url):
    page.goto(url, wait_until='domcontentloaded', timeout=45000)
    page.wait_for_timeout(2500)
    urls = page.locator('img').evaluate_all("""imgs => imgs.flatMap(img => {
      const values=[img.currentSrc,img.src,img.dataset.src,img.dataset.lazySrc];
      for(const s of [img.srcset,img.dataset.srcset]) if(s) values.push(...s.split(',').map(x=>x.trim().split(/\\s+/)[0]));
      return values;
    }).filter(Boolean)""")
    unique=[]
    for photo_url in urls:
        if photo_url.startswith('https://img.kleinanzeigen.de/') and photo_url not in unique:
            unique.append(photo_url)
    photos=[]
    for photo_url in unique:
        response=page.context.request.get(photo_url, headers={'Referer':url}, timeout=30000)
        if response.ok:
            body=response.body()
            if len(body)>15000:
                photos.append((photo_url, body, response.headers.get('content-type','image/jpeg')))
        if len(photos)==4:
            break
    if len(photos)<1:
        raise ValueError('actual listing photos unavailable')
    return photos

def classify(api_key, photos):
    parts=[{'text':PROMPT}]
    parts += [{'inlineData':{'mimeType':mime.split(';')[0], 'data':base64.b64encode(body).decode()}} for _,body,mime in photos]
    payload=json.dumps({'contents':[{'parts':parts}],'generationConfig':{'responseMimeType':'application/json','temperature':0}}).encode()
    request=Request(f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={api_key}', data=payload, headers={'Content-Type':'application/json'})
    with urlopen(request, timeout=90) as response:
        result=json.load(response)
    text=result['candidates'][0]['content']['parts'][0]['text'].strip().removeprefix('```json').removesuffix('```').strip()
    answer=json.loads(text)
    required=('is_xt600z_3aj','is_red_white','is_complete_motorcycle','confidence','reason')
    if any(k not in answer for k in required) or not 0 <= float(answer['confidence']) <= 1:
        raise ValueError('invalid Gemini result')
    return answer

def run():
    api_key=os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise SystemExit('GEMINI_API_KEY is required')
    listings_path=ROOT/'data/listings.json'; cache_path=ROOT/'data/vision_cache.json'; report_path=ROOT/'data/last-run.json'
    data=json.loads(listings_path.read_text(encoding='utf-8'))
    cache=json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
    rows={x['id']:x for group in ('listings','candidates','inactive_listings') for x in data.get(group,[])}
    stats={'run_at':datetime.now(timezone.utc).isoformat(),'candidates_found':0,'photos_loaded':0,'gemini_checked':0,'verified_matches':0,'errors':[]}
    candidates=[x for x in rows.values() if x.get('active') is True and not x.get('visually_verified_3aj') and plausible(x)]
    stats['candidates_found']=len(candidates)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True); page=browser.new_page(locale='de-DE')
        for row in candidates[:MAX_CHECKS]:
            try:
                photos=extract_photos(page,row['listing_url']); stats['photos_loaded']+=len(photos)
                hashes=[hashlib.sha256(body).hexdigest() for _,body,_ in photos]
                cached=cache.get(row['id'])
                if cached and cached.get('image_hashes')==hashes and cached.get('result'):
                    answer=cached['result']
                else:
                    answer=classify(api_key,photos); stats['gemini_checked']+=1
                    cache[row['id']]={'listing_url':row['listing_url'],'image_hashes':hashes,'result':answer,'verified_at':datetime.now(timezone.utc).isoformat(),'model':MODEL}
                yes=(answer['is_xt600z_3aj'] is True and answer['is_red_white'] is True and answer['is_complete_motorcycle'] is True and float(answer['confidence'])>=THRESHOLD)
                row.update(images=[u for u,_,_ in photos],image_url=photos[0][0],visually_verified_3aj=yes,red_white=yes,review_status='approved' if yes else 'rejected',visual_verification={**answer,'model':MODEL,'verified_at':cache[row['id']]['verified_at'],'image_hashes':hashes})
                stats['verified_matches']+=int(yes)
            except Exception as error:
                stats['errors'].append({'id':row['id'],'error':str(error)})
        browser.close()
    data['listings']=[x for x in rows.values() if x.get('active') and x.get('visually_verified_3aj')]
    data['inactive_listings']=[x for x in rows.values() if x.get('active') is False]
    data['candidates']=[x for x in rows.values() if x.get('active') is not False and not x.get('visually_verified_3aj')]
    listings_path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    cache_path.write_text(json.dumps(cache,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report_path.write_text(json.dumps(stats,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(stats,ensure_ascii=False))

if __name__=='__main__': run()
