"""Record a human review only after inspecting exact listing photographs."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from search import fetch, parse
from verify import evidence, RULE_VERSION

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('url')
p.add_argument('--evidence', required=True, help='Observed model, colour and completeness features')
p.add_argument('--approve', action='store_true', required=True, help='Confirm you inspected the photos, not just seller text')
a = p.parse_args()
listing = parse(a.url, *fetch(a.url))
if not listing['active'] or listing['excluded_by_text']:
    raise SystemExit('Listing is not eligible')
sha = evidence(listing)
path = Path(__file__).resolve().parents[1] / 'data/visual_reviews.json'
reviews = json.loads(path.read_text(encoding='utf-8'))
reviews[listing['id']] = {'decision':'approved','rule_version':RULE_VERSION,'listing_url':listing['listing_url'],
 'image_url':listing['image_url'],'image_sha256':sha,'reviewed_at':datetime.now(timezone.utc).isoformat(),
 'reviewer':'manual','evidence':a.evidence,'red_white':True,'whole_motorcycle':True,'visually_verified_3aj':True}
path.write_text(json.dumps(reviews,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Saved image-bound review for', listing['id'])

