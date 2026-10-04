"""Главная страница /home: статусы, серии, прочитано по месяцам (данные из Hardcover)."""
import json

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from hardcover import gql

router = APIRouter()

QUERY = """
query {
  me {
    user_books(limit: 1000) {
      status_id
      rating
      book {
        title
        pages
        image { url }
        featured_book_series { position series { id name books_count } }
      }
      user_book_reads { finished_at }
    }
  }
}
"""


async def fetch_books() -> list:
    me = (await gql(QUERY))["data"]["me"]
    me = me[0] if isinstance(me, list) else me
    out = []
    for ub in me["user_books"]:
        b = ub["book"]
        link = b.get("featured_book_series") or {}
        s = link.get("series") or {}
        dates = [x["finished_at"] for x in ub["user_book_reads"] if x.get("finished_at")]
        out.append({
            "t": b["title"], "c": (b.get("image") or {}).get("url"),
            "p": b.get("pages") or 0, "s": ub["status_id"], "r": ub.get("rating"),
            "d": max(dates) if dates else None,
            "si": s.get("id"), "sn": s.get("name"),
            "sp": link.get("position"), "st": s.get("books_count"),
        })
    return out


@router.get("/", response_class=HTMLResponse)
async def home():
    data = json.dumps(await fetch_books(), ensure_ascii=False).replace("</", "<\\/")
    return PAGE.replace("__DATA__", data)


PAGE = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Мои книги</title>
<style>
:root{--bg:#0b1020;--card:#111a2e;--text:#e8ecf5;--mut:#8b95ab;--line:#232e48}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,system-ui,sans-serif;background:var(--bg);color:var(--text)}
body::before{content:"";position:fixed;inset:0;z-index:-1;background:
radial-gradient(600px 400px at 8% 0,#4f86f044,transparent),
radial-gradient(500px 400px at 92% 8%,#d9569a33,transparent),
radial-gradient(700px 500px at 50% 100%,#5046e533,transparent)}
.wrap{max-width:1100px;margin:0 auto;padding:1.5rem 1rem 4rem}
h1{margin:0 0 1rem;font-size:1.8rem}
h2{font-size:1.1rem;margin:0 0 .8rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:1.1rem 1.2rem;margin-bottom:1.2rem}
.pills{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.8rem;margin-bottom:1.2rem}
.pill{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:.9rem 1rem}
.pill b{font-size:1.9rem;display:block}.pill span{color:var(--mut);font-size:.85rem}
.row{display:flex;gap:.8rem;overflow-x:auto;padding-bottom:.4rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:.9rem}
.book{width:100px;flex:0 0 100px}.grid .book{width:auto}
.book img,.nc{width:100%;aspect-ratio:2/3;object-fit:cover;border-radius:8px;display:block;background:#4f86f0}
.nc{display:flex;align-items:center;justify-content:center;font-size:2rem}
.bt{font-size:.75rem;margin-top:.3rem;line-height:1.2;color:var(--mut)}
.series{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:1rem 1.5rem}
.s-top{display:flex;justify-content:space-between;font-weight:600}.s-top span{color:var(--mut);font-weight:400}
.bar{height:8px;background:#2c3650;border-radius:4px;margin:.4rem 0 .2rem;overflow:hidden}
.bar i{display:block;height:100%;border-radius:4px}.s-sub{color:var(--mut);font-size:.8rem}
.tools{display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:.8rem}
button,select{background:#1a2540;color:var(--text);border:1px solid var(--line);border-radius:10px;padding:.4rem .8rem;font:inherit;cursor:pointer}
button.on{background:#4f86f0;border-color:#4f86f0}
.chart{display:flex;gap:.5rem;height:200px}
.col{flex:1;display:flex;flex-direction:column;align-items:center;position:relative;cursor:pointer}
.track{flex:1;width:100%;display:flex;align-items:flex-end;justify-content:center}
.fill{width:70%;max-width:44px;border-radius:6px 6px 0 0;min-height:3px;transition:filter .15s}
.col:hover .fill{filter:brightness(1.3)}.col small{color:var(--mut);font-size:.7rem}.val{font-size:.75rem;height:1em}
.col:hover::after{content:attr(data-tip);position:absolute;top:-8px;background:#000c;padding:.3rem .5rem;border-radius:8px;font-size:.75rem;white-space:nowrap;z-index:2}
#picked{margin-top:1rem}#picked h3{font-size:.95rem;color:var(--mut);font-weight:500}
</style></head><body><div class="wrap">
<h1>📚 Мои книги</h1>
<div class="pills" id="pills"></div>
<div class="card"><h2>Читаю сейчас</h2><div class="row" id="reading"></div></div>
<div class="card"><h2>Серии</h2><div class="series" id="series"></div></div>
<div class="card"><h2>Прочитано по месяцам</h2>
<div class="tools"><select id="yr"></select><button id="mb" class="on">Книги</button><button id="mp">Страницы</button></div>
<div class="chart" id="chart"></div><div id="picked"></div></div>
<div class="card"><div class="tools" id="tabs"></div><div class="grid" id="shelf"></div></div>
</div><script>
const B=__DATA__;
const $=id=>document.getElementById(id);
const el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e};
const MONTHS=['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'];
const COLORS=['#4f86f0','#5046e5','#d9569a','#e3b23c','#5cc16a','#e8793a'];
const by=s=>B.filter(b=>b.s===s);
const NOW=new Date().getFullYear();
function cover(b){const w=el('div','book');w.title=b.t;
 if(b.c){const i=el('img');i.src=b.c;i.loading='lazy';w.append(i)}else w.append(el('div','nc',b.t[0]));
 w.append(el('div','bt',b.t));return w}

// счётчики
const read=by(3);
[[read.length,'прочитано всего'],[read.filter(b=>b.d&&+b.d.slice(0,4)===NOW).length,'в '+NOW+' году'],
 [by(2).length,'читаю сейчас'],[by(1).length,'хочу прочитать']].forEach(([n,t])=>{
 const p=el('div','pill');p.append(el('b','',n),el('span','',t));$('pills').append(p)});

by(2).forEach(b=>$('reading').append(cover(b)));
if(!by(2).length)$('reading').append(el('span','s-sub','Сейчас ничего не читаешь'));

// серии
const S={};
B.forEach(b=>{if(!b.si)return;const s=S[b.si]??={n:b.sn,t:b.st||0,r:0,cur:false};
 if(b.s===3)s.r++;if(b.s===2)s.cur=true});
const rank=s=>s.cur?0:(s.t&&s.r>=s.t?2:1);
Object.values(S).sort((a,b)=>rank(a)-rank(b)||(b.r/(b.t||1))-(a.r/(a.t||1))||a.n.localeCompare(b.n))
.forEach((s,i)=>{const pct=s.t?Math.min(100,Math.round(s.r/s.t*100)):0;const d=el('div');
 const top=el('div','s-top',s.n);top.append(el('span','',pct+'%'));
 const bar=el('div','bar');const f=el('i');f.style.width=pct+'%';f.style.background=COLORS[i%6];bar.append(f);
 d.append(top,bar,el('div','s-sub',`${s.r} из ${s.t||'?'} книг`+(s.cur?' · читаю':'')));$('series').append(d)});

// по месяцам
let mode='b',yr=NOW;
const years=[...new Set(read.filter(b=>b.d).map(b=>+b.d.slice(0,4)).concat(NOW))].sort((a,b)=>b-a);
years.forEach(y=>$('yr').append(new Option(y,y)));
$('yr').onchange=e=>{yr=+e.target.value;chart();$('picked').replaceChildren()};
$('mb').onclick=()=>setMode('b');$('mp').onclick=()=>setMode('p');
function setMode(m){mode=m;$('mb').classList.toggle('on',m==='b');$('mp').classList.toggle('on',m==='p');chart()}
function chart(){
 const m=Array.from({length:12},()=>({n:0,p:0,l:[]}));
 read.filter(b=>b.d&&+b.d.slice(0,4)===yr).forEach(b=>{const x=m[+b.d.slice(5,7)-1];x.n++;x.p+=b.p;x.l.push(b)});
 const v=x=>mode==='b'?x.n:x.p,mx=Math.max(1,...m.map(v));$('chart').replaceChildren();
 m.forEach((x,i)=>{const c=el('div','col'),t=el('div','track'),f=el('div','fill');
  f.style.height=(v(x)/mx*100)+'%';f.style.background=COLORS[i%6];t.append(f);
  c.dataset.tip=`${MONTHS[i]}: ${x.n} книг, ${x.p} стр.`;c.append(el('span','val',v(x)||''),t,el('small','',MONTHS[i]));
  c.onclick=()=>{const p=$('picked');p.replaceChildren(el('h3','',`${MONTHS[i]} ${yr}: ${x.n} книг · ${x.p} стр.`));
   const r=el('div','row');x.l.forEach(b=>r.append(cover(b)));p.append(r)};
  $('chart').append(c)})}
chart();

// полки
const TABS=[['Прочитано',3],['Читаю',2],['Хочу прочитать',1],['Брошено',5]];
function shelf(s,btn){[...$('tabs').children].forEach(b=>b.classList.toggle('on',b===btn));$('shelf').replaceChildren();
 by(s).sort((a,b)=>(b.d||'').localeCompare(a.d||'')).forEach(b=>$('shelf').append(cover(b)))}
TABS.forEach(([n,s],i)=>{const b=el('button','',`${n} (${by(s).length})`);b.onclick=()=>shelf(s,b);$('tabs').append(b);if(!i)shelf(s,b)});
</script></body></html>"""
