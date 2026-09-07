const $ = id => document.getElementById(id);
const money = n => new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(n);
const date = s => s ? new Intl.DateTimeFormat('ru-RU',{dateStyle:'short',timeStyle:'short',timeZone:'Europe/Berlin'}).format(new Date(s)) + ' · Berlin' : 'ещё не выполнялась';
const el = (tag, cls, text) => { const e=document.createElement(tag); if(cls)e.className=cls; if(text!==undefined)e.textContent=text; return e; };
let records=[];
function eligible(x){try{const u=new URL(x.listing_url);return x.active===true && x.visually_verified_3aj===true && x.red_white===true && Date.now()-Date.parse(x.last_seen)<36*3600000 && u.hostname==='www.kleinanzeigen.de' && /^\/s-anzeige\/[^/]+\/\d+-305-\d+$/.test(u.pathname);}catch{return false;}}
function render(){
 $('cards').replaceChildren(); const items=records.filter(eligible).sort((a,b)=>$('sort').value==='price'?(a.price_eur??Infinity)-(b.price_eur??Infinity):Date.parse(b.date_listed||b.first_seen)-Date.parse(a.date_listed||a.first_seen));
 let shown=items.length; $('count').textContent=shown; $('empty').hidden=shown>0;
 for(const x of items){
  const card=el('article','card'),photo=el('div','photo');if(x.image_url){const img=el('img');img.src=x.image_url;img.alt=x.title+' — фото объявления '+x.id;img.loading='lazy';img.referrerPolicy='no-referrer';img.addEventListener('error',()=>{img.remove();photo.prepend(el('div','photo-unavailable','Фото временно недоступно'));});photo.append(img);}else photo.append(el('div','photo-unavailable','Фото временно недоступно'));
  const badges=el('div','badges');if(Date.now()-Date.parse(x.first_seen)<48*3600000)badges.append(el('span','badge','NEW'));
  if(x.previous_price_eur!=null && x.price_eur!=null && x.price_eur<x.previous_price_eur)badges.append(el('span','badge drop','−'+money(x.previous_price_eur-x.price_eur)));photo.append(badges);
  const body=el('div','card-body');body.append(el('p','price',x.price_eur==null?'Цена не указана':money(x.price_eur)),el('h3','',x.title),el('p','city',x.city||'Город не указан'));
  const specs=el('dl','specs');for(const [label,value] of [['Регистрация',x.registration||'—'],['Пробег',x.mileage_km==null?'—':new Intl.NumberFormat('de-DE').format(x.mileage_km)+' км']]){const d=el('div');d.append(el('dt','',label),el('dd','',value));specs.append(d);}body.append(specs);
  const confidence=x.visual_verification?.confidence;body.append(el('p','verified','✓ 3AJ visually verified'+(confidence!=null?' · '+Math.round(confidence*100)+'%':'')));
  const actions=el('div','actions'),link=el('a','open','Open in Kleinanzeigen ↗');link.href=x.app_share_url||x.listing_url;link.target='_blank';link.rel='noopener noreferrer';
  actions.append(link);body.append(actions,el('p','checked','Проверено: '+date(x.last_seen)));card.append(photo,body);$('cards').append(card);
 }
}
$('sort').addEventListener('change',render);
const dataUrl='https://imartyanov.github.io/xt600seach/data/listings.json?t='+Date.now();
fetch(dataUrl,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error();return r.json();}).then(data=>{records=data.listings||[];$('updated').textContent='Обновлено: '+date(data.last_updated);if(data.run_status!=='ok'){$('notice').hidden=false;$('notice').textContent='Поиск выполнен не полностью. Показаны только уже подтверждённые объявления.';}render();setInterval(render,60000);}).catch(()=>{$('updated').textContent='Не удалось загрузить данные';$('notice').hidden=false;$('notice').textContent='Попробуйте обновить страницу позже.';});
