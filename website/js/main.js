/* ═══ FinRo.ro — Main JS ═══ */
document.addEventListener('DOMContentLoaded',()=>{initHeader();initSearch();initCounters();initTickerDuplicate();initCookieBanner()});

function initHeader(){
    const h=document.getElementById('header');
    window.addEventListener('scroll',()=>{h.style.boxShadow=window.scrollY>100?'0 2px 20px rgba(0,0,0,0.4)':'none'},{passive:true});
    const m=document.getElementById('menuToggle'),n=document.getElementById('mainNav');
    if(m)m.addEventListener('click',()=>{n.classList.toggle('active');m.classList.toggle('active')});
}

function initSearch(){
    const t=document.getElementById('searchToggle'),o=document.getElementById('searchOverlay'),c=document.getElementById('searchClose'),i=document.getElementById('searchInput');
    if(!t||!o)return;
    t.addEventListener('click',()=>{o.classList.toggle('active');if(o.classList.contains('active'))setTimeout(()=>i.focus(),200)});
    c.addEventListener('click',()=>o.classList.remove('active'));
    document.addEventListener('keydown',e=>{if(e.key==='Escape')o.classList.remove('active');if((e.ctrlKey||e.metaKey)&&e.key==='k'){e.preventDefault();o.classList.toggle('active');if(o.classList.contains('active'))setTimeout(()=>i.focus(),200)}});
}

function initCounters(){
    const obs=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){animateCounter(e.target);obs.unobserve(e.target)}})},{threshold:0.5});
    document.querySelectorAll('[data-count]').forEach(c=>obs.observe(c));
}

function animateCounter(el){
    const target=parseInt(el.dataset.count),dur=2000,start=performance.now();
    (function update(now){
        const p=Math.min((now-start)/dur,1),eased=1-Math.pow(1-p,3),cur=Math.floor(eased*target);
        el.textContent=target>=1000?cur.toLocaleString('ro-RO'):cur;
        if(p<1)requestAnimationFrame(update);else el.textContent=(target>=1000?target.toLocaleString('ro-RO'):target)+'+';
    })(start);
}

function initTickerDuplicate(){const c=document.getElementById('tickerContent');if(c)c.innerHTML+=c.innerHTML}

function calculateCredit(){
    const a=+document.getElementById('creditAmount').value,r=+document.getElementById('creditRate').value/100,y=+document.getElementById('creditYears').value;
    const m=y*12,mr=r/12,mp=a*(mr*Math.pow(1+mr,m))/(Math.pow(1+mr,m)-1),tot=mp*m,int=tot-a;
    const el=document.getElementById('creditResult');
    el.innerHTML=`<div style="margin-bottom:8px">📌 <strong>Rata lunară: ${fRON(mp)}</strong></div><div>💰 Total: <strong>${fRON(tot)}</strong></div><div>📊 Dobândă: <strong>${fRON(int)}</strong></div><div style="color:var(--text-muted);font-size:0.82rem;margin-top:8px">* Orientativ, fără comisioane.</div>`;
    el.classList.add('active');
}

function calculateSavings(){
    const ini=+document.getElementById('savingsInit').value,mo=+document.getElementById('savingsMonthly').value,r=+document.getElementById('savingsRate').value/100,y=+document.getElementById('savingsYears').value;
    const mr=r/12,ms=y*12;let bal=ini,dep=ini;
    for(let i=0;i<ms;i++){bal=bal*(1+mr)+mo;dep+=mo}
    const el=document.getElementById('savingsResult');
    el.innerHTML=`<div style="margin-bottom:8px">📌 <strong>Valoare finală: ${fRON(bal)}</strong></div><div>💵 Depus: <strong>${fRON(dep)}</strong></div><div>📈 Dobândă: <strong>${fRON(bal-dep)}</strong></div><div style="color:var(--text-muted);font-size:0.82rem;margin-top:8px">* Dobândă compusă, fără impozit 10%.</div>`;
    el.classList.add('active');
}

function fRON(v){return new Intl.NumberFormat('ro-RO',{style:'currency',currency:'RON',minimumFractionDigits:0,maximumFractionDigits:0}).format(v)}

function initCookieBanner(){if(getCk('finro_ck'))document.getElementById('cookieBanner').classList.add('hidden')}
function acceptCookies(){setCk('finro_ck','1',365);document.getElementById('cookieBanner').classList.add('hidden')}
function manageCookies(){alert('Setări cookie-uri — în dezvoltare')}
function setCk(n,v,d){document.cookie=`${n}=${v};expires=${new Date(Date.now()+d*864e5).toUTCString()};path=/;SameSite=Lax`}
function getCk(n){return document.cookie.split('; ').reduce((r,v)=>{const p=v.split('=');return p[0]===n?p[1]:r},'')}

function handleNewsletter(e){
    e.preventDefault();const i=e.target.querySelector('input'),b=e.target.querySelector('button'),o=b.textContent;
    i.value='';b.textContent='✓ Mulțumim!';b.style.background='#34D399';
    setTimeout(()=>{b.textContent=o;b.style.background=''},3000);return false;
}
