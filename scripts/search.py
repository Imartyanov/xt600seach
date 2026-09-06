"""Replaceable Kleinanzeigen HTTP/search/parser adapter. No visual inference here."""
import re
import time
import os
import hashlib
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, urljoin, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from bs4 import BeautifulSoup

SHARE = '?utm_source=copyToPasteboard&utm_campaign=socialbuttons&utm_medium=social&utm_content=app_ios'
PATTERN = re.compile(r'^/s-anzeige/[^/]+/(\d+)-305-(\d+)/?$')

def identity(url):
    p = urlsplit(url)
    m = PATTERN.fullmatch(p.path)
    if p.scheme != 'https' or p.hostname != 'www.kleinanzeigen.de' or not m:
        raise ValueError('Not an exact motorcycle listing URL: ' + url)
    return m.group(1), urlunsplit(('https', p.netloc, p.path.rstrip('/'), '', ''))

def fetch(url):
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; YamahaMonitor/1.0)', 'Accept-Language': 'de-DE,de;q=0.9'})
    try:
        with urlopen(request, timeout=25) as response:
            body = response.read()
            if os.environ.get('MONITOR_CACHE_DIR'):
                cache = Path(os.environ['MONITOR_CACHE_DIR'])
                cache.mkdir(parents=True, exist_ok=True)
                key = hashlib.sha256(url.encode()).hexdigest()
                (cache / key).write_bytes(body)
                (cache / (key + '.url')).write_text(url, encoding='utf-8')
            return response.status, response.url, body
    except HTTPError as error:
        if error.code in (404, 410):
            return error.code, error.url, b''
        raise

def search(config, errors):
    found = set(config['seed_urls'])
    for query in config['queries']:
        for page in range(1, config['max_pages_per_query'] + 1):
            url = 'https://www.kleinanzeigen.de/s-motorraeder-roller/' + (f'seite:{page}/' if page > 1 else '') + quote(query.replace(' ', '-')) + '/k0c305'
            try:
                time.sleep(config['request_delay_seconds'])
                status, final, body = fetch(url)
                soup = BeautifulSoup(body, 'html.parser')
                container = soup.select_one('#srchrslt-adtable')
                if status != 200 or container is None:
                    raise ValueError('Search unavailable or markup changed')
                links = container.select('a[href^="/s-anzeige/"]')
                if not links and not re.search(r'keine (anzeigen|ergebnisse)|0 ergebnisse', soup.get_text(' ',strip=True), re.I):
                    raise ValueError('No listing links; search markup needs review')
                for item in links:
                    candidate = urljoin(url, item['href'])
                    try:
                        _, exact = identity(candidate)
                        found.add(exact)
                    except ValueError:
                        pass
                print(f'Search {query} page {page}: {len(found)} unique listing URLs', flush=True)
                if not any(re.search(r'/seite(?::|%3A)' + str(page+1) + r'/', a['href'], re.I) for a in soup.select('a[href]')):
                    break
                if page == config['max_pages_per_query']:
                    errors.append({'url': url, 'error': 'Search page limit reached; coverage incomplete'})
            except Exception as error:
                errors.append({'url': url, 'error': str(error)})
                break
    return found

def parse(url, status, final, body):
    ad_id, exact = identity(url)
    if status in (404, 410):
        return {'id': ad_id, 'active': False, 'reason': str(status)}
    if status != 200:
        raise ValueError('Unexpected HTTP status')
    # A redirect onto a general result/category page means the ad is gone.
    path = urlsplit(final).path
    if final != url and (path.startswith('/s-motorraeder-roller') or path.startswith('/s-anzeigen') or path == '/' or '/k0' in path):
        return {'id': ad_id, 'active': False, 'reason': 'redirect_to_results'}
    final_id, canonical = identity(final)
    if final_id != ad_id:
        raise ValueError('Redirect to another listing')
    soup = BeautifulSoup(body, 'html.parser')
    title = soup.select_one('#viewad-title')
    if not title or not soup.select_one('#viewad-main-info'):
        raise ValueError('Listing not confirmed; challenge or changed markup')
    if soup.select_one('.sold-label, .viewad-sold, #viewad-sold') or title.select_one('.sold') or re.search(rb'contactPosterEnabled\s*:\s*false', body):
        return {'id': ad_id, 'active': False, 'reason': 'sold'}
    box = soup.select_one('#viewad-ad-id-box')
    if not box or ad_id not in box.get_text():
        raise ValueError('Page listing ID mismatch')
    details = {}
    for li in soup.select('#viewad-details li'):
        val = li.select_one('.addetailslist--detail--value')
        if val:
            details[li.get_text(' ', strip=True).replace(val.get_text(' ', strip=True), '').strip()] = val.get_text(' ', strip=True)
    registration = details.get('Erstzulassung', '')
    months = 'Januar Februar März April Mai Juni Juli August September Oktober November Dezember'.split()
    parts = registration.split()
    registration = f'{parts[1]}-{months.index(parts[0])+1:02}' if len(parts) == 2 and parts[0] in months else registration if re.fullmatch(r'\d{4}', registration) else None
    price = soup.select_one('#viewad-main-info meta[itemprop="price"]')
    price_text = price.get('content','') if price else ''
    photo = soup.select_one('meta[property="og:image"]')
    image_url = photo.get('content') if photo else None
    if image_url and urlsplit(image_url).hostname != 'img.kleinanzeigen.de':
        image_url = None
    date_el = soup.select_one('#viewad-extra-info')
    date_match = re.search(r'\b(\d{2})\.(\d{2})\.(\d{4})\b', date_el.get_text() if date_el else '')
    description = soup.select_one('#viewad-description-text')
    text = description.get_text(' ', strip=True) if description else ''
    locality = soup.select_one('#viewad-locality')
    title_text = title.get_text(' ', strip=True)
    excluded = bool(re.search(r'\b(suche|gesuch|schlachtfest|schlachtfahrzeug|teileträger|ersatzteile|rahmen ohne|motor ohne)\b', title_text, re.I))
    return {'id': ad_id, 'title': title_text, 'price_eur': int(float(price_text)) if re.fullmatch(r'\d+(?:\.\d+)?', price_text) else None,
            'city': locality.get_text(' ', strip=True) if locality else None, 'registration': registration,
            'mileage_km': int(re.sub(r'\D', '', details['Kilometerstand'])) if re.search(r'\d', details.get('Kilometerstand', '')) else None,
            'date_listed': '-'.join(reversed(date_match.groups())) if date_match else None,
            'listing_url': canonical, 'app_share_url': canonical + SHARE, 'image_url': image_url,
            'active': True, 'description': text, 'excluded_by_text': excluded}

