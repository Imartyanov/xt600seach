"""Fail-closed, image-bound manual verification gate for the MVP."""
import hashlib
from io import BytesIO
from urllib.parse import urlsplit
from PIL import Image
from search import fetch

RULE_VERSION = 1

def evidence(listing):
    url = listing.get('image_url')
    if not url or urlsplit(url).scheme != 'https' or urlsplit(url).hostname != 'img.kleinanzeigen.de':
        raise ValueError('No reliable exact-listing image')
    status, final, body = fetch(url)
    if status != 200 or urlsplit(final).hostname != 'img.kleinanzeigen.de':
        raise ValueError('Photo unavailable')
    with Image.open(BytesIO(body)) as image:
        image.load()
        if min(image.size) < 450:
            raise ValueError('Photo too small for verification')
    return hashlib.sha256(body).hexdigest()

def approved(listing, reviews, sha):
    review = reviews.get(listing['id'], {})
    return (not listing.get('excluded_by_text') and review.get('rule_version') == RULE_VERSION
            and review.get('image_sha256') == sha and review.get('image_url') == listing.get('image_url')
            and review.get('listing_url') == listing.get('listing_url')
            and review.get('decision') == 'approved' and review.get('red_white') is True
            and review.get('whole_motorcycle') is True and review.get('visually_verified_3aj') is True
            and bool(review.get('evidence')) and bool(review.get('reviewed_at')))

