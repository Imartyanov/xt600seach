"""Copy only public assets; do not publish source, reviews or error logs."""
import json
import shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
out = ROOT / 'dist'
out.mkdir(exist_ok=True)
shutil.copy2(ROOT / 'index.html', out / 'index.html')
shutil.copytree(ROOT / 'assets', out / 'assets', dirs_exist_ok=True)
(out / 'data').mkdir(exist_ok=True)
data = json.loads((ROOT / 'data/listings.json').read_text(encoding='utf-8'))
public = {k:data.get(k) for k in ('last_updated','last_attempt','run_status','search_complete','discovered_count','reviewed_count','listings')}
public['listings'] = [{k:v for k,v in x.items() if k not in ('description','price_history')} for x in public['listings']]
(out / 'data/listings.json').write_text(json.dumps(public, ensure_ascii=False, indent=2),encoding='utf-8')
(out / 'data/current.json').write_text(json.dumps(public['listings'], ensure_ascii=False, indent=2),encoding='utf-8')
all_rows=[{k:v for k,v in x.items() if k not in ('description','price_history')} for group in ('listings','candidates','inactive_listings') for x in data.get(group,[])]
(out / 'data/all-listings.json').write_text(json.dumps(all_rows, ensure_ascii=False, indent=2),encoding='utf-8')
report=ROOT/'data/last-run.json'
if report.exists(): shutil.copy2(report,out/'data/last-run.json')
(out / '.nojekyll').touch()
print('Built dist/')
