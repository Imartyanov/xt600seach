"""Apply image-bound visual decisions to already fetched records, without claiming a new live check."""
import json
from pathlib import Path
from verify import approved, RULE_VERSION

ROOT = Path(__file__).resolve().parents[1]

def apply_reviews():
    path = ROOT / 'data/listings.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    reviews = json.loads((ROOT / 'data/visual_reviews.json').read_text(encoding='utf-8'))
    rows = {x['id']: x for group in ('listings','candidates','inactive_listings') for x in data.get(group,[])}
    for row in rows.values():
        if not row.get('active') or row.get('check_status') != 'ok':
            continue
        review = reviews.get(row['id'], {})
        yes = bool(approved(row, reviews, row.get('image_sha256')))
        row['visually_verified_3aj'] = yes
        row['red_white'] = yes
        current = (review.get('image_sha256') == row.get('image_sha256')
                   and review.get('image_url') == row.get('image_url')
                   and review.get('listing_url') == row.get('listing_url')
                   and review.get('rule_version') == RULE_VERSION)
        row['review_status'] = 'approved' if yes else 'rejected' if current and review.get('decision') == 'rejected' else 'needs_review'
    data['listings'] = [r for r in rows.values() if r.get('active') and r.get('visually_verified_3aj')]
    data['inactive_listings'] = [r for r in rows.values() if r.get('active') is False]
    data['candidates'] = [r for r in rows.values() if r.get('active') is not False and not r.get('visually_verified_3aj')]
    data['reviewed_count'] = sum(r.get('review_status') in ('approved','rejected') for r in rows.values())
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temp.replace(path)
    print(f'{len(data["listings"])} verified; {data["reviewed_count"]} visually reviewed')

if __name__ == '__main__':
    apply_reviews()

