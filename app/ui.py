from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse


router = APIRouter()

_PAGE_TITLES = {
    "developer": "Developer Console",
    "finance": "Finance Console",
    "fde": "FDE Debug Console",
    "vcc": "VCC Agent",
}

_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{TITLE}} · DemoAI</title>
  <style>
    :root{--bg:#f4f7fb;--ink:#172033;--muted:#68738a;--card:#fff;--line:#e3e8f0;--brand:#405cf5;--good:#16875d;--warn:#b36b00;--bad:#c43d56}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    .shell{display:flex;min-height:100vh}.side{width:230px;background:#121a2d;color:#dfe6ff;padding:25px 16px}.brand{font-size:20px;font-weight:750;padding:0 12px 4px}.sub{color:#91a0c6;font-size:12px;padding:0 12px 24px}.nav{display:block;color:#b6c2e2;text-decoration:none;padding:11px 12px;border-radius:9px;margin:3px 0}.nav:hover,.nav.active{background:#27345a;color:#fff}.main{flex:1;max-width:1180px;padding:30px 38px}.top{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px}.title{font-size:27px;font-weight:750}.badge{background:#e8f8f0;color:var(--good);padding:5px 10px;border-radius:999px;font-size:12px}.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:16px}.card{grid-column:span 12;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;box-shadow:0 2px 8px #20305a08}.half{grid-column:span 6}.third{grid-column:span 4}.metric{font-size:30px;font-weight:750;margin:5px 0}.muted{color:var(--muted)}label{display:block;font-size:12px;color:var(--muted);margin:10px 0 5px}input,textarea,select{width:100%;padding:10px 11px;border:1px solid #ccd4e2;border-radius:8px;background:#fff;color:var(--ink);font:inherit}textarea{min-height:100px;resize:vertical}button{border:0;border-radius:8px;padding:10px 15px;background:var(--brand);color:#fff;font-weight:650;cursor:pointer;margin:12px 5px 0 0}button.secondary{background:#e9edf6;color:#283652}button.good{background:var(--good)}button.warn{background:#c77a08}button:disabled{opacity:.55;cursor:not-allowed}.row{display:flex;gap:10px;align-items:end}.row>*{flex:1}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;margin-top:10px}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);white-space:nowrap}th{color:var(--muted);font-size:12px}.status{font-weight:700}.status.SUCCEEDED,.status.ACTIVE{color:var(--good)}.status.PROCESSING,.status.PENDING_APPROVAL{color:var(--warn)}.status.FAILED,.status.REJECTED{color:var(--bad)}pre{background:#111827;color:#d7e1ff;border-radius:9px;padding:14px;overflow:auto;min-height:60px}.notice{padding:11px 13px;background:#fff8e7;border:1px solid #f1d59b;border-radius:9px;color:#80520d;margin-bottom:16px}.small{font-size:12px}.actions{margin-top:10px}.empty{color:var(--muted);padding:20px 0}@media(max-width:800px){.side{width:190px}.main{padding:22px 16px}.half,.third{grid-column:span 12}}
  </style>
</head>
<body>
<div class="shell"><aside class="side"><div class="brand">DemoAI</div><div class="sub">PingPong FDE POC · Mock</div>
  <a class="nav" data-page="developer" href="/ui/developer">Developer</a><a class="nav" data-page="finance" href="/ui/finance">Finance</a><a class="nav" data-page="fde" href="/ui/fde">FDE Debug</a><a class="nav" data-page="vcc" href="/ui/vcc">VCC Agent</a>
  <div class="sub" style="margin-top:25px">Local demo only<br>Sandbox: Pending</div>
</aside><main class="main"><div class="top"><div class="title">{{TITLE}}</div><span class="badge">MOCK_VERIFIED</span></div><div class="notice small">这是本地 Mock 演示界面，不处理真实资金。角色 Token 仅用于 POC：Developer / Finance / Approver / Admin。</div><div id="app"></div></main></div>
<script>
const PAGE='{{PAGE}}'; const API='/api';
const TOKENS={developer:'dev-token',finance:'finance-token',approver:'approver-token',admin:'admin-token',fde:'fde-token'};
function token(role){return localStorage.getItem('demo-token-'+role)||TOKENS[role]}
function auth(role){return {'Authorization':'Bearer '+token(role)}}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function api(path,options={}){const res=await fetch(API+path,options); let data={}; try{data=await res.json()}catch{} if(!res.ok)throw new Error(data.detail||('HTTP '+res.status)); return data}
function setApp(html){document.getElementById('app').innerHTML=html}
function table(rows,headers,render){if(!rows.length)return '<div class="empty">暂无记录</div>';return '<div class="table-wrap"><table><thead><tr>'+headers.map(x=>'<th>'+x+'</th>').join('')+'</tr></thead><tbody>'+rows.map(render).join('')+'</tbody></table></div>'}
function money(v){return v==null?'—':Number(v).toFixed(2)+' USD'}
async function hmac(body){const key=await crypto.subtle.importKey('raw',new TextEncoder().encode('local-demo-secret'),{name:'HMAC',hash:'SHA-256'},false,['sign']);const sig=await crypto.subtle.sign('HMAC',key,new TextEncoder().encode(body));return [...new Uint8Array(sig)].map(x=>x.toString(16).padStart(2,'0')).join('')}

async function developer(){setApp(`<div class="grid"><section class="card third"><div class="muted">Available Credits</div><div class="metric" id="balance">—</div><div class="muted small">USD_CREDIT</div></section><section class="card half"><h3>充值</h3><div class="row"><div><label>金额（USD）</label><input id="amount" value="100.00" inputmode="decimal"></div><button onclick="topup()">创建充值订单</button></div><pre id="topup-result">提交后显示 Payment 与 next_action</pre></section><section class="card"><h3>Payment History</h3><div id="payments">加载中…</div></section></div>`);await refreshDeveloper()}
async function refreshDeveloper(){try{const b=await api('/me/credits',{headers:auth('developer')});document.getElementById('balance').textContent=money(b.available_balance);const rows=await api('/payments',{headers:auth('developer')});document.getElementById('payments').innerHTML=table(rows,['Payment','Amount','Status','Provider'],r=>`<tr><td>${esc(r.payment_id)}</td><td>${money(r.amount)}</td><td class="status ${esc(r.payment_status)}">${esc(r.payment_status)}</td><td>${esc(r.provider_status||'—')}</td></tr>`)}catch(e){toast(e.message)}}
async function topup(){try{const amount=document.getElementById('amount').value;const d=await api('/topups',{method:'POST',headers:{...auth('developer'),'Content-Type':'application/json','Idempotency-Key':'ui-'+Date.now()},body:JSON.stringify({amount,currency:'USD'})});document.getElementById('topup-result').textContent=JSON.stringify(d,null,2);localStorage.setItem('last-payment',d.payment_id);const button=document.createElement('button');button.className='good';button.textContent='模拟 SUCCESS Webhook';button.onclick=()=>mockSuccess(d.payment_id,amount);document.getElementById('topup-result').after(button);await refreshDeveloper()}catch(e){toast(e.message)}}
async function mockSuccess(paymentId,amount){try{const body=JSON.stringify({partner_transaction_id:'txn_'+paymentId,status:'SUCCESS',amount,currency:'USD'});const sig=await hmac(body);const d=await fetch('/api/webhooks/pingpong/checkout',{method:'POST',headers:{'Content-Type':'application/json','X-Mock-Signature':sig},body});if(!d.ok)throw new Error('Webhook HTTP '+d.status);toast('SUCCESS Webhook 已处理');await refreshDeveloper()}catch(e){toast(e.message)}}

async function finance(){setApp(`<div class="grid"><section class="card"><h3>交易与退款</h3><div id="payments">加载中…</div><div class="row"><div><label>Payment ID</label><input id="refund-payment" placeholder="选择上方 Payment"></div><button class="warn" onclick="refund()">发起全额退款</button></div><pre id="refund-result"></pre></section><section class="card half"><h3>快捷入口</h3><p class="muted">退款要求 Payment 已 SUCCEEDED，且 Credits 可用余额足够。</p><a href="/ui/vcc"><button>打开 VCC Agent</button></a></section></div>`);try{const rows=await api('/payments',{headers:auth('finance')});document.getElementById('payments').innerHTML=table(rows,['Payment','User','Amount','Status','Refunded'],r=>`<tr><td><button class="secondary small" onclick="document.getElementById('refund-payment').value='${esc(r.payment_id)}'">${esc(r.payment_id)}</button></td><td>DemoAI</td><td>${money(r.amount)}</td><td class="status ${esc(r.payment_status)}">${esc(r.payment_status)}</td><td>—</td></tr>`)}catch(e){toast(e.message)}}
async function refund(){try{const id=document.getElementById('refund-payment').value;const d=await api('/refunds',{method:'POST',headers:{...auth('finance'),'Content-Type':'application/json','Idempotency-Key':'ui-refund-'+id},body:JSON.stringify({payment_id:id})});document.getElementById('refund-result').textContent=JSON.stringify(d,null,2)}catch(e){toast(e.message)}}

async function fde(){setApp(`<div class="grid"><section class="card"><h3>主动查单</h3><div class="row"><div><label>Payment ID</label><input id="reconcile-id" placeholder="payment_xxx"></div><button onclick="reconcile()">Reconcile</button></div><pre id="reconcile-result"></pre></section><section class="card half"><h3>Provider Calls</h3><div id="calls">加载中…</div></section><section class="card half"><h3>Webhook Events</h3><div id="webhooks">加载中…</div></section><section class="card"><h3>Audit Log</h3><div id="audit">加载中…</div></section></div>`);await refreshFde()}
async function refreshFde(){try{const h=auth('admin');const [calls,webhooks,audit]=await Promise.all([api('/admin/provider-calls',{headers:h}),api('/admin/webhooks',{headers:h}),api('/admin/audit',{headers:h})]);document.getElementById('calls').innerHTML=table(calls,['Operation','Trace','HTTP','Result'],r=>`<tr><td>${esc(r.operation)}</td><td>${esc(r.trace_id).slice(0,12)}…</td><td>${esc(r.http_status||'—')}</td><td>${r.success?'OK':esc(r.error_type||'ERR')}</td></tr>`);document.getElementById('webhooks').innerHTML=table(webhooks,['Event','Status','Provider Status'],r=>`<tr><td>${esc(r.event_key)}</td><td class="status ${esc(r.status)}">${esc(r.status)}</td><td>${esc(r.provider_status||'—')}</td></tr>`);document.getElementById('audit').innerHTML=table(audit,['Action','Resource','Outcome','Trace'],r=>`<tr><td>${esc(r.action)}</td><td>${esc(r.resource_type)} ${esc(r.resource_id||'')}</td><td>${esc(r.outcome)}</td><td>${esc(r.trace_id).slice(0,12)}…</td></tr>`)}catch(e){toast(e.message)}}
async function reconcile(){try{const id=document.getElementById('reconcile-id').value;const d=await api('/admin/payments/'+encodeURIComponent(id)+'/reconcile',{method:'POST',headers:auth('admin')});document.getElementById('reconcile-result').textContent=JSON.stringify(d,null,2);await refreshFde()}catch(e){toast(e.message)}}

async function vcc(){setApp(`<div class="grid"><section class="card half"><h3>自然语言申请</h3><textarea id="vcc-message">为 AWS 9 月账单申请一张 20000 USD 的虚拟卡，有效期 30 天</textarea><button onclick="parseVcc()">解析并检查预算</button><pre id="vcc-result"></pre></section><section class="card half"><h3>Approval / Card Tool</h3><p class="muted small">大于 1,000 USD 必须使用 Approver Token 人工确认。</p><label>Application ID</label><input id="application-id" placeholder="解析后自动填充"><div class="actions"><button class="good" onclick="approveVcc()">Approver Confirm</button><button onclick="createCard()">Create VCC</button></div><pre id="card-result"></pre></section></div>`)}
async function parseVcc(){try{const d=await api('/vcc/agent',{method:'POST',headers:{...auth('finance'),'Content-Type':'application/json'},body:JSON.stringify({message:document.getElementById('vcc-message').value})});document.getElementById('vcc-result').textContent=JSON.stringify(d,null,2);if(d.application_id)document.getElementById('application-id').value=d.application_id}catch(e){toast(e.message)}}
async function approveVcc(){try{const id=document.getElementById('application-id').value;const d=await api('/vcc/'+encodeURIComponent(id)+'/approve',{method:'POST',headers:{...auth('approver'),'Content-Type':'application/json'},body:JSON.stringify({approved:true})});document.getElementById('card-result').textContent=JSON.stringify(d,null,2)}catch(e){toast(e.message)}}
async function createCard(){try{const id=document.getElementById('application-id').value;const d=await api('/vcc/'+encodeURIComponent(id)+'/card',{method:'POST',headers:auth('finance')});document.getElementById('card-result').textContent=JSON.stringify(d,null,2)}catch(e){toast(e.message)}}
function toast(message){let el=document.getElementById('toast');if(!el){el=document.createElement('div');el.id='toast';el.style='position:fixed;right:22px;bottom:22px;background:#172033;color:#fff;padding:12px 16px;border-radius:8px;z-index:4';document.body.appendChild(el)}el.textContent=message;setTimeout(()=>el.remove(),3500)}
document.querySelectorAll('.nav').forEach(a=>{if(a.dataset.page===PAGE)a.classList.add('active')});
({developer,finance,fde,vcc}[PAGE]||developer)();
</script></body></html>'''


def page(name: str) -> HTMLResponse:
    return HTMLResponse(_HTML.replace("{{TITLE}}", _PAGE_TITLES[name]).replace("{{PAGE}}", name))


@router.get("/ui", include_in_schema=False)
def ui_home():
    return RedirectResponse("/ui/developer")


@router.get("/ui/{name}", include_in_schema=False)
def ui_page(name: str):
    if name not in _PAGE_TITLES:
        return RedirectResponse("/ui/developer")
    return page(name)

