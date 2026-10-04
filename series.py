"""Страница /series: все серии с обложками и прогрессом."""
import json

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from dashboard import fetch_books

router = APIRouter()


@router.get("/series", response_class=HTMLResponse)
async def series_page():
    data = json.dumps(await fetch_books(), ensure_ascii=False).replace("</", "<\\/")
    return PAGE.replace("__DATA__", data)


PAGE = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Серии</title>
<style>
:root{--bg:#0b1020;--card:#111a2e;--text:#e8ecf5;--mut:#8b95ab;--line:#232e48}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,system-ui,sans-serif;background:var(--bg);color:var(--text)}
body::before{content:"";position:fixed;inset:0;z-index:-1;background:
radial-gradient(600px 400px at 8% 0,#4f86f044,transparent),
radial-gradient(500px 400px at 92% 8%,#d9569a33,transparent)}
.wrap{max-width:1100px;margin:0 auto;padding:1.5rem 1rem 4rem}
a{color:#7aa2ff;text-decoration:none}h1{margin:.5rem 0 1rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:1.1rem 1.2rem;margin-bottom:1.2rem}
.top{display:flex;justify-content:space-between;font-weight:600}.top span{color:var(--mut);font-weight:400}
.bar{height:8px;background:#2c3650;border-radius:4px;margin:.5rem 0 1rem;overflow:hidden}
.bar i{display:block;height:100%;border-radius:4px}
.row{display:flex;gap:.8rem;overflow-x:auto;padding-bottom:.4rem}
.book{flex:0 0 90px;width:90px}
.book img,.nc{width:100%;aspect-ratio:2/3;object-fit:cover;border:3px solid transparent;border-radius:8px;display:block;background:#4f86f0}
.nc{display:flex;align-items:center;justify-content:center;font-size:2rem}
.st-3 img,.st-3 .nc{border-color:#5cc16a}.st-2 img,.st-2 .nc{border-color:#4f86f0}
.st-4 img,.st-4 .nc{border-color:#e3b23c}.st-5 img,.st-5 .nc{border-color:#d9569a;opacity:.6}
.st-1 img,.st-1 .nc{opacity:.5}
.n{font-size:.75rem;color:var(--mut);margin-top:.3rem}.t{font-size:.78rem;line-height:1.2}
</style></head><body><div class="wrap">
<a href="/">← Главная</a><h1>Мои серии</h1><div id="list"></div>
</div><script>
const B=__DATA__;
const el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e};
const COLORS=['#4f86f0','#5046e5','#d9569a','#e3b23c','#5cc16a','#e8793a'];
const S={};
B.forEach(b=>{if(!b.si)return;const s=S[b.si]??={n:b.sn,t:b.st||0,r:0,cur:false,l:[]};
 s.l.push(b);if(b.s===3)s.r++;if(b.s===2)s.cur=true});
const rank=s=>s.cur?0:(s.t&&s.r>=s.t?2:1);
Object.values(S).sort((a,b)=>rank(a)-rank(b)||a.n.localeCompare(b.n)).forEach((s,i)=>{
 const pct=s.t?Math.min(100,Math.round(s.r/s.t*100)):0,c=el('div','card');
 const top=el('div','top',s.n);top.append(el('span','',`${s.r} из ${s.t||'?'} книг`));
 const bar=el('div','bar'),f=el('i');f.style.width=pct+'%';f.style.background=COLORS[i%6];bar.append(f);
 const row=el('div','row');
 s.l.sort((a,b)=>(a.sp??999)-(b.sp??999)).forEach(b=>{const w=el('div','book st-'+b.s);w.title=b.t;
  if(b.c){const im=el('img');im.src=b.c;im.loading='lazy';w.append(im)}else w.append(el('div','nc',b.t[0]));
  w.append(el('div','n',b.sp!=null?'#'+b.sp:''),el('div','t',b.t));row.append(w)});
 c.append(top,bar,row);document.getElementById('list').append(c)});
</script></body></html>"""
