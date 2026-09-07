"""Search broadly, verify every candidate, preserve history on transient failures."""
import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from search import search, fetch, parse, identity
from verify import approved

ROOT = Path(__file__).resolve().parents[1]

def now():
    return datetime.now(timezone.utc).isoformat()

def merge(old, fresh, stamp):
    result = {**old, **fresh, 'first_seen': old.get('first_seen', stamp), 'last_checked': stamp, 'check_status': 'ok'}
    if fresh['active']:
        result.pop('inactive_since', None)
        result['last_seen'] = stamp
        result['previous_price_eur'] = old.get('previous_price_eur')
        result['price_history'] = list(old.get('price_history', []))
        price = fresh.get('price_eur')
        if old.get('price_eur') is not None and price is not None and old['price_eur'] != price:
            result['previous_price_eur'] = old['price_eur']
            result['price_changed_at'] = stamp
        if price is not None and (not result['price_history'] or result['price_history'][-1]['price_eur'] != price):
            result['price_history'].append({'at': stamp, 'price_eur': price})
    else:
        result['inactive_since'] = old.get('inactive_since', stamp)
    return result

def update(seed_only=False):
    path = ROOT / 'data/listings.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    reviews = json.loads((ROOT / 'data/visual_reviews.json').read_text(encoding='utf-8'))
    config = json.loads((ROOT / 'config/search.json').read_text(encoding='utf-8'))
    errors, stamp = [], now()
    records = {x['id']: x for group in ('listings', 'inactive_listings', 'candidates') for x in data.get(group, [])}
    urls = set(config['seed_urls']) if seed_only else search(config, errors)
    discovered_urls = set(urls)
    search_complete = not seed_only and not errors
    urls.update(x['listing_url'] for x in records.values() if x.get('listing_url'))
    by_id = {}
    for url in urls:
        ad_id, exact = identity(url)
        by_id[ad_id] = exact
    succeeded = 0
    for index, (ad_id, url) in enumerate(sorted(by_id.items()), 1):
        print(f'Checking {ad_id} ({index}/{len(by_id)})', flush=True)
        old = records.get(ad_id, {})
        try:
            # A known URL present in today's search is still active. Reuse its parsed
            # details and visual-review result; fetch the detail page only for new
            # ads or when an old URL disappeared from search.
            if not seed_only and old and url in discovered_urls and old.get('active') is True:
                records[ad_id] = {**old, 'last_checked': stamp, 'last_seen': stamp,
                                  'check_status': 'cached'}
                succeeded += 1
                continue
            time.sleep(config['request_delay_seconds'])
            fresh = parse(url, *fetch(url))
            if fresh['active']:
                # Visual verification is performed separately from actual rendered photos.
                verified = bool(old.get('visually_verified_3aj') and old.get('image_url') == fresh.get('image_url'))
                fresh.update(image_sha256=old.get('image_sha256'), visually_verified_3aj=verified, red_white=verified,
                             review_status='approved' if verified else 'needs_review')
            records[ad_id] = merge(old, fresh, now())
            succeeded += 1
        except Exception as error:
            logging.warning('%s: %s', ad_id, error)
            errors.append({'id': ad_id, 'url': url, 'error': str(error)})
            if old:
                # Keep a matching manual approval through transient network failures.
                # The approval remains bound to the exact listing URL and image hash.
                verified = bool(old.get('active') and (
                    old.get('visually_verified_3aj')
                    or approved(old, reviews, old.get('image_sha256'))
                ))
                records[ad_id] = {
                    **old,
                    'last_checked': stamp,
                    'check_status': 'error',
                    'visually_verified_3aj': verified,
                    'red_white': verified,
                    'review_status': 'approved' if verified else old.get('review_status', 'needs_review'),
                }
            else:
                records[ad_id] = {'id': ad_id, 'listing_url': url, 'active': None,
                                  'first_seen': stamp, 'last_checked': stamp, 'check_status': 'error'}
    stamp = now()
    data['last_attempt'] = stamp
    if succeeded:
        data['last_updated'] = stamp
    data['last_full_search'] = stamp if search_complete else data.get('last_full_search')
    data['search_complete'] = search_complete
    data['discovered_count'] = len(by_id)
    data['run_status'] = 'partial' if errors or seed_only else 'ok'
    data['errors'] = errors
    data['listings'] = [x for x in records.values() if x.get('active') and x.get('visually_verified_3aj')]
    data['inactive_listings'] = [x for x in records.values() if x.get('active') is False]
    data['candidates'] = [x for x in records.values() if x.get('active') is not False and not x.get('visually_verified_3aj')]
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)
    print(f'{succeeded} checked; {len(data["listings"])} verified; {len(data["candidates"])} pending; {len(errors)} errors')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed-only', action='store_true', help='Check seed/history only; mark search incomplete')
    update(parser.parse_args().seed_only)
