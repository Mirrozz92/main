"""Custom glassmorphism API documentation served at /docs.

Self-contained dark/cyan glass-themed page documenting the public Publisher API:
GET /me, POST /request-op, POST /check-resource, and webhooks. Includes
language tabs (curl / Python / JS), success + error response examples,
copy-to-clipboard, scroll-spy sidebar. No external CDN.

Internal-only endpoints (cryptobot webhook, onboarding/register forms) are
deliberately excluded.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["meta"])

_BASE_URL = "https://fastsub.95-85-251-42.sslip.io"

_HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FastSub API</title>
<style>
:root{
  --bg:#05080f; --bg2:#070b14; --glass:rgba(18,28,48,.55);
  --glass-border:rgba(96,165,250,.18); --glass-hi:rgba(120,180,255,.08);
  --text:#e3ecfb; --muted:#7e8ca8; --blue:#3b82f6; --cyan:#22d3ee;
  --cyan-soft:#67e8f9; --line:rgba(96,165,250,.12); --code:rgba(4,8,16,.7);
  --mono:'SF Mono',ui-monospace,'JetBrains Mono','Fira Code',Menlo,monospace;
  --sans:'Inter','Segoe UI',system-ui,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:var(--sans);
  line-height:1.65;font-size:15px;overflow-x:hidden}
/* animated background */
body::before{content:"";position:fixed;inset:0;z-index:-2;
  background:
    radial-gradient(900px 600px at 12% -5%,rgba(34,211,238,.10),transparent 60%),
    radial-gradient(800px 700px at 95% 8%,rgba(59,130,246,.12),transparent 55%),
    radial-gradient(700px 700px at 50% 110%,rgba(34,211,238,.07),transparent 60%),
    var(--bg)}
body::after{content:"";position:fixed;inset:0;z-index:-1;opacity:.4;
  background-image:linear-gradient(var(--line) 1px,transparent 1px),
    linear-gradient(90deg,var(--line) 1px,transparent 1px);
  background-size:48px 48px;
  mask-image:radial-gradient(circle at 50% 30%,#000,transparent 80%)}
a{color:var(--cyan);text-decoration:none}
a:hover{color:var(--cyan-soft)}
code{font-family:var(--mono);font-size:.9em}

.layout{display:flex;min-height:100vh}
/* glass sidebar */
.sidebar{width:280px;position:fixed;top:0;bottom:0;left:0;overflow-y:auto;
  padding:30px 0;backdrop-filter:blur(20px) saturate(140%);
  -webkit-backdrop-filter:blur(20px) saturate(140%);
  background:linear-gradient(180deg,rgba(10,16,30,.75),rgba(6,10,18,.6));
  border-right:1px solid var(--glass-border)}
.brand{padding:0 26px 24px;display:flex;align-items:center;gap:12px}
.brand .logo{width:38px;height:38px;border-radius:11px;
  background:linear-gradient(135deg,var(--cyan),var(--blue));
  display:grid;place-items:center;font-weight:800;color:#02060d;font-size:20px;
  box-shadow:0 4px 24px rgba(34,211,238,.4),inset 0 1px 0 rgba(255,255,255,.3)}
.brand .name{font-weight:750;font-size:18px;letter-spacing:.2px}
.brand .ver{font-size:11px;color:var(--cyan);font-family:var(--mono);opacity:.8}
.nav{padding:8px 14px}
.nav .group{font-size:10.5px;text-transform:uppercase;letter-spacing:.16em;
  color:var(--muted);padding:18px 12px 7px;font-weight:600}
.nav a{display:flex;align-items:center;gap:9px;padding:9px 13px;border-radius:10px;
  color:var(--text);font-size:14px;opacity:.82;transition:.18s;
  border:1px solid transparent}
.nav a:hover{background:var(--glass-hi);opacity:1;
  border-color:var(--glass-border);transform:translateX(3px)}
.nav a.active{background:linear-gradient(90deg,rgba(34,211,238,.14),transparent);
  border-color:var(--glass-border);opacity:1}
.nav .m{font-family:var(--mono);font-size:10px;font-weight:800;
  padding:2px 7px;border-radius:6px;letter-spacing:.04em}
.m.get{background:rgba(34,211,238,.15);color:var(--cyan)}
.m.post{background:rgba(59,130,246,.18);color:#93c5fd}

.main{margin-left:280px;flex:1;max-width:960px;padding:60px 60px 140px}
.hero{margin-bottom:60px;animation:rise .7s cubic-bezier(.2,.7,.3,1) both}
.badge{display:inline-flex;align-items:center;gap:7px;font-family:var(--mono);
  font-size:12px;padding:6px 14px;border-radius:30px;color:var(--cyan);
  margin-bottom:24px;background:var(--glass);border:1px solid var(--glass-border);
  backdrop-filter:blur(12px)}
.badge::before{content:"";width:7px;height:7px;border-radius:50%;
  background:var(--cyan);box-shadow:0 0 10px var(--cyan);animation:pulse 2s infinite}
.hero h1{font-size:46px;font-weight:800;letter-spacing:-1px;margin-bottom:14px;
  background:linear-gradient(135deg,#fff 20%,var(--cyan-soft));
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.hero p{color:var(--muted);font-size:18px;max-width:660px}

section{margin-bottom:64px;scroll-margin-top:30px}
.card{background:var(--glass);border:1px solid var(--glass-border);
  border-radius:20px;padding:32px 34px;backdrop-filter:blur(16px) saturate(130%);
  -webkit-backdrop-filter:blur(16px) saturate(130%);
  box-shadow:0 12px 40px rgba(0,0,0,.35),inset 0 1px 0 rgba(255,255,255,.05)}
section h2{font-size:28px;font-weight:750;margin-bottom:14px;letter-spacing:-.4px}
section h3{font-size:16px;font-weight:650;margin:24px 0 11px;color:var(--cyan-soft)}
section p{color:#aebbd2;margin-bottom:14px}

.endpoint{display:flex;align-items:center;gap:13px;margin:8px 0 18px;
  font-family:var(--mono);padding:13px 18px;border-radius:13px;
  background:var(--code);border:1px solid var(--glass-border)}
.method{font-weight:800;font-size:12px;padding:5px 12px;border-radius:8px}
.method.get{background:rgba(34,211,238,.16);color:var(--cyan)}
.method.post{background:rgba(59,130,246,.2);color:#93c5fd}
.path{font-size:15px;color:var(--text)}

table{width:100%;border-collapse:collapse;margin:14px 0;font-size:13.5px}
th,td{text-align:left;padding:11px 14px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase;
  letter-spacing:.08em}
td code{background:rgba(34,211,238,.1);padding:2px 7px;border-radius:6px;
  color:var(--cyan-soft)}
.req{color:#fb7185;font-size:10.5px;font-family:var(--mono);font-weight:700}
.opt{color:var(--muted);font-size:10.5px;font-family:var(--mono)}

.code{background:var(--code);border:1px solid var(--glass-border);
  border-radius:15px;margin:16px 0;overflow:hidden;
  backdrop-filter:blur(8px);box-shadow:0 8px 30px rgba(0,0,0,.3)}
.code .tabs{display:flex;gap:3px;padding:8px 8px 0;
  background:rgba(8,14,26,.5);border-bottom:1px solid var(--line)}
.code .tab{font-family:var(--mono);font-size:12.5px;padding:9px 16px;
  cursor:pointer;color:var(--muted);border-radius:9px 9px 0 0;transition:.16s;
  border:1px solid transparent;border-bottom:none;
  user-select:none;-webkit-user-select:none;-webkit-tap-highlight-color:transparent;
  position:relative;overflow:hidden}
.code .tab:hover{color:var(--text)}
.code .tab.active{color:var(--cyan);background:var(--code);
  border-color:var(--glass-border)}
.code .tab:active{transform:scale(.96)}
.code .body{position:relative}
.code pre{padding:20px 22px;overflow-x:auto;font-family:var(--mono);
  font-size:13px;line-height:1.7;color:#bcccea}
.code pre:not(.active){display:none}
.copy{position:absolute;top:11px;right:11px;background:var(--glass);
  border:1px solid var(--glass-border);color:var(--muted);font-family:var(--mono);
  font-size:11px;padding:6px 12px;border-radius:8px;cursor:pointer;transition:.16s;
  backdrop-filter:blur(8px);
  user-select:none;-webkit-user-select:none;-webkit-tap-highlight-color:transparent;
  position:absolute;overflow:hidden}
.copy:hover{color:var(--cyan);border-color:var(--cyan);
  box-shadow:0 0 16px rgba(34,211,238,.25)}
.copy:active{transform:scale(.94)}
.copy.done{color:#34d399;border-color:#34d399}
/* ripple effect on click */
.ripple{position:absolute;border-radius:50%;transform:scale(0);
  background:rgba(34,211,238,.4);pointer-events:none;
  animation:ripple .55s ease-out}
@keyframes ripple{to{transform:scale(2.5);opacity:0}}
/* nav links also unselectable */
.nav a{user-select:none;-webkit-user-select:none;
  -webkit-tap-highlight-color:transparent}
.tok-k{color:#7dd3fc}.tok-s{color:#67e8f9}.tok-c{color:#5b6b85}
.tok-n{color:#93c5fd}.tok-b{color:#fbbf24}

.resp-label{display:inline-flex;align-items:center;gap:7px;font-family:var(--mono);
  font-size:12px;font-weight:700;margin:18px 0 2px;padding:4px 12px;border-radius:8px}
.resp-label.ok{background:rgba(52,211,153,.13);color:#34d399}
.resp-label.err{background:rgba(251,113,133,.13);color:#fb7185}

.callout{background:linear-gradient(90deg,rgba(34,211,238,.08),transparent);
  border:1px solid var(--glass-border);border-left:3px solid var(--cyan);
  border-radius:12px;padding:16px 20px;margin:18px 0;font-size:14px;color:#bccce0}
.callout b{color:var(--cyan-soft)}

@keyframes rise{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:none}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
section{animation:rise .6s cubic-bezier(.2,.7,.3,1) both}
@media(max-width:860px){
  /* burger + slide-in sidebar */
  .burger{display:grid}
  .sidebar{transform:translateX(-100%);width:84vw;max-width:320px;z-index:50;
    transition:transform .3s cubic-bezier(.3,.7,.2,1);
    box-shadow:0 0 60px rgba(0,0,0,.6)}
  body.nav-open .sidebar{transform:translateX(0)}
  .overlay{display:block}
  body.nav-open .overlay{opacity:1;pointer-events:auto}
  .main{margin-left:0;padding:74px 18px 80px;max-width:100%}
  .card{padding:20px 18px;border-radius:16px}
  .hero h1{font-size:32px}
  .hero p{font-size:15px}
  .badge{margin-bottom:18px}
  section{margin-bottom:40px}
  section h2{font-size:22px}
  /* tables scroll horizontally */
  .card table{display:block;overflow-x:auto;white-space:nowrap;
    -webkit-overflow-scrolling:touch}
  /* code blocks: bigger touch targets, smaller font */
  .code pre{font-size:12px;padding:16px 16px}
  .code .tab{padding:11px 15px;font-size:13px}
  .copy{padding:8px 13px;font-size:11.5px}
  .endpoint{flex-wrap:wrap;font-size:13px;padding:11px 14px}
  .resp-label{font-size:11px}
}
@media(max-width:420px){
  .hero h1{font-size:27px}
  .main{padding:70px 14px 70px}
  .code pre{font-size:11px}
}
/* burger button (hidden on desktop) */
.burger{display:none;position:fixed;top:14px;left:14px;z-index:60;
  width:46px;height:46px;border-radius:13px;cursor:pointer;
  background:var(--glass);border:1px solid var(--glass-border);
  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
  place-items:center;gap:5px;
  user-select:none;-webkit-user-select:none;-webkit-tap-highlight-color:transparent}
.burger span{display:block;width:20px;height:2px;border-radius:2px;
  background:var(--cyan);transition:.25s}
body.nav-open .burger span:nth-child(1){transform:translateY(7px) rotate(45deg)}
body.nav-open .burger span:nth-child(2){opacity:0}
body.nav-open .burger span:nth-child(3){transform:translateY(-7px) rotate(-45deg)}
/* dark overlay behind slide-in menu */
.overlay{display:none;position:fixed;inset:0;z-index:40;opacity:0;
  pointer-events:none;transition:opacity .3s;
  background:rgba(2,5,11,.6);backdrop-filter:blur(2px)}
</style>
</head>
<body>
<div class="layout">
  <div class="burger" id="burger"><span></span><span></span><span></span></div>
  <div class="overlay" id="overlay"></div>
  <aside class="sidebar">
    <div class="brand">
      <div class="logo">F</div>
      <div><div class="name">FastSub API</div><div class="ver">v0.4.0</div></div>
    </div>
    <nav class="nav" id="nav">
      <div class="group">Начало</div>
      <a href="#intro">Введение</a>
      <a href="#auth">Авторизация</a>
      <a href="#base">Базовый URL</a>
      <div class="group">Эндпоинты</div>
      <a href="#me"><span class="m get">GET</span>/me</a>
      <a href="#request-op"><span class="m post">POST</span>/request-op</a>
      <a href="#check"><span class="m post">POST</span>/check-resource</a>
      <div class="group">Интеграции</div>
      <a href="#quickstart">Быстрый старт</a>
      <a href="#bot-example">Пример бота</a>
      <a href="#webhooks">Webhooks</a>
      <a href="#errors">Коды ошибок</a>
    </nav>
  </aside>
  <main class="main">
    <div class="hero" id="intro">
      <div class="badge">PUBLISHER API · v0.4.0</div>
      <h1>FastSub API</h1>
      <p>Монетизация Telegram-трафика. Запрашивайте задания, проверяйте подписки
         и получайте выплаты. Полный справочник публичного API для партнёров.</p>
    </div>

    <section id="auth"><div class="card">
<h2>Авторизация</h2>
<p>Все запросы к <code>/api/v1/*</code> требуют Bearer-токен. Получить его можно
в боте <a href="https://t.me/fastsub_publisher_bot">@fastsub_publisher_bot</a>.</p>
<div class="code"><div class="tabs"><div class="tab active" onclick="tab(this,0)">HTTP</div></div><div class="body"><button class="copy" onclick="cp(this)">копировать</button><pre class="active"><span class="tok-k">Authorization</span>: Bearer <span class="tok-s">fsp_live_xxxxxxxxxxxxxxxx</span></pre></div></div>
<div class="callout"><b>Важно:</b> токен даёт полный доступ к вашему аккаунту.
Храните его в секрете; при компрометации перевыпустите в боте.</div>
</div></section>
<section id="base"><div class="card">
<h2>Базовый URL</h2>
<div class="code"><div class="tabs"><div class="tab active" onclick="tab(this,0)">URL</div></div><div class="body"><button class="copy" onclick="cp(this)">копировать</button><pre class="active">__BASE__/api/v1</pre></div></div>
</div></section>
<section id="me"><div class="card">
<h2>Информация о партнёре</h2>
<div class="endpoint"><span class="method get">GET</span><span class="path">/api/v1/me</span></div>
<p>Возвращает данные аккаунта: баланс, холд, рейтинг удержания, текущий токен.</p>
<div class="code"><div class="tabs"><div class="tab active" onclick="tab(this,0)">curl</div><div class="tab" onclick="tab(this,1)">Python</div><div class="tab" onclick="tab(this,2)">JS</div></div><div class="body"><button class="copy" onclick="cp(this)">копировать</button><pre class="active"><span class="tok-n">curl</span> __BASE__/api/v1/me \\
  -H <span class="tok-s">"Authorization: Bearer fsp_live_xxx"</span></pre><pre class=""><span class="tok-k">import</span> httpx
r = httpx.get(
    <span class="tok-s">"__BASE__/api/v1/me"</span>,
    headers={<span class="tok-s">"Authorization"</span>: <span class="tok-s">"Bearer fsp_live_xxx"</span>},
)
<span class="tok-n">print</span>(r.json())</pre><pre class=""><span class="tok-k">const</span> r = <span class="tok-k">await</span> fetch(<span class="tok-s">"__BASE__/api/v1/me"</span>, {
  headers: { <span class="tok-s">"Authorization"</span>: <span class="tok-s">"Bearer fsp_live_xxx"</span> }
});
<span class="tok-k">const</span> data = <span class="tok-k">await</span> r.json();</pre></div></div><div class="resp-label ok">200 OK — успех</div><div class="code"><div class="body"><button class="copy" onclick="cp(this)">копировать</button><pre class="active">{
  <span class="tok-k">"id"</span>: <span class="tok-n">1</span>,
  <span class="tok-k">"project_name"</span>: <span class="tok-s">"My Traffic Bot"</span>,
  <span class="tok-k">"tg_username"</span>: <span class="tok-s">"nklabs"</span>,
  <span class="tok-k">"balance_rub"</span>: <span class="tok-s">"152.40"</span>,
  <span class="tok-k">"hold_rub"</span>: <span class="tok-s">"18.00"</span>,
  <span class="tok-k">"total_earned_rub"</span>: <span class="tok-s">"341.90"</span>,
  <span class="tok-k">"is_vip"</span>: <span class="tok-b">false</span>,
  <span class="tok-k">"retention_rate"</span>: <span class="tok-s">"87.50"</span>,
  <span class="tok-k">"current_token"</span>: {
    <span class="tok-k">"id"</span>: <span class="tok-n">3</span>,
    <span class="tok-k">"label"</span>: <span class="tok-s">"main"</span>,
    <span class="tok-k">"prefix"</span>: <span class="tok-s">"fsp_live_03145d"</span>,
    <span class="tok-k">"requests_count"</span>: <span class="tok-n">1284</span>,
    <span class="tok-k">"last_used_at"</span>: <span class="tok-s">"2026-05-23T18:04:11Z"</span>
  }
}</pre></div></div><div class="resp-label err">401 — ошибка авторизации</div><div class="code"><div class="body"><button class="copy" onclick="cp(this)">копировать</button><pre class="active"><span class="tok-c"># HTTP 401 Unauthorized</span>
{
  <span class="tok-k">"detail"</span>: <span class="tok-s">"invalid or revoked token"</span>
}</pre></div></div>
</div></section>
<section id="request-op"><div class="card">
<h2>Запрос заданий</h2>
<div class="endpoint"><span class="method post">POST</span><span class="path">/api/v1/request-op</span></div>
<p>Главный эндпоинт: возвращает подходящие спонсорские задания для пользователя
с учётом таргетинга рекламодателя.</p>
<h3>Параметры тела (JSON)</h3><table>
<tr><th>Поле</th><th>Тип</th><th>Описание</th></tr>
<tr><td><code>user_id</code> <span class="req">required</span></td><td>integer</td><td>Telegram ID пользователя</td></tr>
<tr><td><code>count</code> <span class="opt">optional</span></td><td>int 1–10</td><td>Сколько заданий выдать</td></tr>
<tr><td><code>has_telegram_premium</code> <span class="opt">optional</span></td><td>boolean</td><td>Есть ли Premium</td></tr>
<tr><td><code>has_profile_photo</code> <span class="opt">optional</span></td><td>boolean</td><td>Есть ли фото профиля</td></tr>
<tr><td><code>has_username</code> <span class="opt">optional</span></td><td>boolean</td><td>Есть ли @username</td></tr>
<tr><td><code>has_bio</code> <span class="opt">optional</span></td><td>boolean</td><td>Заполнено ли описание</td></tr>
<tr><td><code>has_stories</code> <span class="opt">optional</span></td><td>boolean</td><td>Есть ли активные истории</td></tr>
</table>
<div class="callout">Поля аудитории опциональны. Если вы их <b>не передали</b>,
кампании, требующие соответствующий признак, не покажутся этому юзеру.</div>
<div class="code"><div class="tabs"><div class="tab active" onclick="tab(this,0)">curl</div><div class="tab" onclick="tab(this,1)">Python</div><div class="tab" onclick="tab(this,2)">JS</div></div><div class="body"><button class="copy" onclick="cp(this)">копировать</button><pre class="active"><span class="tok-n">curl</span> -X POST __BASE__/api/v1/request-op \\
  -H <span class="tok-s">"Authorization: Bearer fsp_live_xxx"</span> \\
  -H <span class="tok-s">"Content-Type: application/json"</span> \\
  -d <span class="tok-s">'{"user_id": 123456789, "count": 3,
       "has_telegram_premium": true}'</span></pre><pre class=""><span class="tok-k">import</span> httpx
r = httpx.post(
    <span class="tok-s">"__BASE__/api/v1/request-op"</span>,
    headers={<span class="tok-s">"Authorization"</span>: <span class="tok-s">"Bearer fsp_live_xxx"</span>},
    json={
        <span class="tok-s">"user_id"</span>: <span class="tok-n">123456789</span>,
        <span class="tok-s">"count"</span>: <span class="tok-n">3</span>,
        <span class="tok-s">"has_telegram_premium"</span>: <span class="tok-k">True</span>,
    },
)
<span class="tok-n">print</span>(r.json())</pre><pre class=""><span class="tok-k">const</span> r = <span class="tok-k">await</span> fetch(<span class="tok-s">"__BASE__/api/v1/request-op"</span>, {
  method: <span class="tok-s">"POST"</span>,
  headers: {
    <span class="tok-s">"Authorization"</span>: <span class="tok-s">"Bearer fsp_live_xxx"</span>,
    <span class="tok-s">"Content-Type"</span>: <span class="tok-s">"application/json"</span>
  },
  body: JSON.stringify({ user_id: <span class="tok-n">123456789</span>, count: <span class="tok-n">3</span> })
});
<span class="tok-k">const</span> data = <span class="tok-k">await</span> r.json();</pre></div></div><div class="resp-label ok">200 OK — задания выданы</div><div class="code"><div class="body"><button class="copy" onclick="cp(this)">копировать</button><pre class="active">{
  <span class="tok-k">"ok"</span>: <span class="tok-b">true</span>,
  <span class="tok-k">"task_id"</span>: <span class="tok-s">"tsk_a1b2c3d4e5f6"</span>,
  <span class="tok-k">"tasks"</span>: [{
    <span class="tok-k">"link_id"</span>: <span class="tok-s">"lnk_a1b2c3d4e5f6"</span>,
    <span class="tok-k">"type"</span>: <span class="tok-s">"channel"</span>,
    <span class="tok-k">"title"</span>: <span class="tok-s">"Example Channel"</span>,
    <span class="tok-k">"username"</span>: <span class="tok-s">"example"</span>,
    <span class="tok-k">"members_count"</span>: <span class="tok-n">1240</span>,
    <span class="tok-k">"invite_link"</span>: <span class="tok-s">"https://t.me/+AbCdEf12345"</span>,
    <span class="tok-k">"start_link"</span>: <span class="tok-b">null</span>,
    <span class="tok-k">"reward_for_publisher"</span>: <span class="tok-s">"1.5000"</span>
  }]
}</pre></div></div><div class="resp-label ok">200 OK — заданий нет / нужен онбординг</div><div class="code"><div class="body"><button class="copy" onclick="cp(this)">копировать</button><pre class="active"><span class="tok-c"># ok=false, заданий нет</span>
{
  <span class="tok-k">"ok"</span>: <span class="tok-b">false</span>,
  <span class="tok-k">"reason"</span>: <span class="tok-s">"no_tasks"</span>,
  <span class="tok-k">"tasks"</span>: []
}

<span class="tok-c"># нужен онбординг юзера</span>
{
  <span class="tok-k">"ok"</span>: <span class="tok-b">false</span>,
  <span class="tok-k">"reason"</span>: <span class="tok-s">"onboarding_required"</span>,
  <span class="tok-k">"onboarding_url"</span>: <span class="tok-s">"https://fastsub.../onboard/abc123"</span>
}</pre></div></div>
</div></section>
<section id="check"><div class="card">
<h2>Проверка подписки</h2>
<div class="endpoint"><span class="method post">POST</span><span class="path">/api/v1/check-resource</span></div>
<p>Проверяет текущий статус выданного задания по <code>link_id</code>.</p>
<h3>Параметры тела (JSON)</h3>
<table><tr><th>Поле</th><th>Тип</th><th>Описание</th></tr>
<tr><td><code>link_id</code> <span class="req">required</span></td><td>string</td><td>Идентификатор из request-op</td></tr></table>
<div class="code"><div class="tabs"><div class="tab active" onclick="tab(this,0)">curl</div><div class="tab" onclick="tab(this,1)">Python</div><div class="tab" onclick="tab(this,2)">JS</div></div><div class="body"><button class="copy" onclick="cp(this)">копировать</button><pre class="active"><span class="tok-n">curl</span> -X POST __BASE__/api/v1/check-resource \\
  -H <span class="tok-s">"Authorization: Bearer fsp_live_xxx"</span> \\
  -H <span class="tok-s">"Content-Type: application/json"</span> \\
  -d <span class="tok-s">'{"link_id": "lnk_a1b2c3d4e5f6"}'</span></pre><pre class=""><span class="tok-k">import</span> httpx
r = httpx.post(
    <span class="tok-s">"__BASE__/api/v1/check-resource"</span>,
    headers={<span class="tok-s">"Authorization"</span>: <span class="tok-s">"Bearer fsp_live_xxx"</span>},
    json={<span class="tok-s">"link_id"</span>: <span class="tok-s">"lnk_a1b2c3d4e5f6"</span>},
)
<span class="tok-n">print</span>(r.json())</pre><pre class=""><span class="tok-k">const</span> r = <span class="tok-k">await</span> fetch(<span class="tok-s">"__BASE__/api/v1/check-resource"</span>, {
  method: <span class="tok-s">"POST"</span>,
  headers: {
    <span class="tok-s">"Authorization"</span>: <span class="tok-s">"Bearer fsp_live_xxx"</span>,
    <span class="tok-s">"Content-Type"</span>: <span class="tok-s">"application/json"</span>
  },
  body: JSON.stringify({ link_id: <span class="tok-s">"lnk_a1b2c3d4e5f6"</span> })
});</pre></div></div><div class="resp-label ok">200 OK — статус получен</div><div class="code"><div class="body"><button class="copy" onclick="cp(this)">копировать</button><pre class="active">{
  <span class="tok-k">"ok"</span>: <span class="tok-b">true</span>,
  <span class="tok-k">"link_id"</span>: <span class="tok-s">"lnk_a1b2c3d4e5f6"</span>,
  <span class="tok-k">"status"</span>: <span class="tok-s">"subscribed"</span>
}</pre></div></div><h3>Возможные статусы</h3><table>
<tr><th>status</th><th>Значение</th></tr>
<tr><td><code>pending</code></td><td>Выдано, подписка ещё не зафиксирована</td></tr>
<tr><td><code>subscribed</code></td><td>Подписался (hold-период)</td></tr>
<tr><td><code>verified</code></td><td>Подтверждено, начислено</td></tr>
<tr><td><code>unsubscribed</code></td><td>Отписался</td></tr>
<tr><td><code>expired</code></td><td>TTL вышел без подписки</td></tr>
<tr><td><code>reverted</code></td><td>Финальная отмена</td></tr>
<tr><td><code>paid</code></td><td>Выплачено</td></tr>
<tr><td><code>invalid</code></td><td>Некорректное состояние</td></tr>
</table><div class="resp-label err">Ошибки (403 / 404)</div><div class="code"><div class="body"><button class="copy" onclick="cp(this)">копировать</button><pre class="active"><span class="tok-c"># HTTP 404 — link_id не найден</span>
{
  <span class="tok-k">"detail"</span>: <span class="tok-s">"link_id not found: lnk_xxx"</span>
}

<span class="tok-c"># HTTP 403 — чужой link_id</span>
{
  <span class="tok-k">"detail"</span>: <span class="tok-s">"this link_id belongs to a different publisher"</span>
}</pre></div></div>
</div></section>
<section id="quickstart"><div class="card">
<h2>Быстрый старт</h2>
<p>Базовая функция запроса заданий и проверки подписки. Скопируйте и
используйте как основу интеграции.</p>
<div class="code">
<div class="tabs">
<div class="tab active" onclick="tab(this,0)">Python</div>
<div class="tab" onclick="tab(this,1)">JS</div>
</div>
<div class="body"><button class="copy" onclick="cp(this)">копировать</button>
<pre class="active"><span class="tok-k">import</span> httpx

API = <span class="tok-s">"__BASE__/api/v1"</span>
TOKEN = <span class="tok-s">"fsp_live_xxx"</span>
HEADERS = {<span class="tok-s">"Authorization"</span>: <span class="tok-s">f"Bearer {TOKEN}"</span>}


<span class="tok-k">def</span> <span class="tok-n">request_tasks</span>(user_id: int, count: int = <span class="tok-n">3</span>) -> dict:
    <span class="tok-c"># Запросить задания для пользователя</span>
    r = httpx.post(<span class="tok-s">f"{API}/request-op"</span>, headers=HEADERS,
                   json={<span class="tok-s">"user_id"</span>: user_id, <span class="tok-s">"count"</span>: count})
    <span class="tok-k">return</span> r.json()


<span class="tok-k">def</span> <span class="tok-n">check_subscription</span>(link_id: str) -> str:
    <span class="tok-c"># Проверить статус подписки по link_id</span>
    r = httpx.post(<span class="tok-s">f"{API}/check-resource"</span>, headers=HEADERS,
                   json={<span class="tok-s">"link_id"</span>: link_id})
    data = r.json()
    <span class="tok-k">return</span> data.get(<span class="tok-s">"status"</span>)  <span class="tok-c"># pending/subscribed/verified/...</span></pre>
<pre><span class="tok-k">const</span> API = <span class="tok-s">"__BASE__/api/v1"</span>;
<span class="tok-k">const</span> TOKEN = <span class="tok-s">"fsp_live_xxx"</span>;
<span class="tok-k">const</span> HEADERS = {
  <span class="tok-s">"Authorization"</span>: <span class="tok-s">`Bearer ${TOKEN}`</span>,
  <span class="tok-s">"Content-Type"</span>: <span class="tok-s">"application/json"</span>
};

<span class="tok-k">async function</span> <span class="tok-n">requestTasks</span>(userId, count = <span class="tok-n">3</span>) {
  <span class="tok-k">const</span> r = <span class="tok-k">await</span> fetch(<span class="tok-s">`${API}/request-op`</span>, {
    method: <span class="tok-s">"POST"</span>, headers: HEADERS,
    body: JSON.stringify({ user_id: userId, count })
  });
  <span class="tok-k">return</span> r.json();
}

<span class="tok-k">async function</span> <span class="tok-n">checkSubscription</span>(linkId) {
  <span class="tok-k">const</span> r = <span class="tok-k">await</span> fetch(<span class="tok-s">`${API}/check-resource`</span>, {
    method: <span class="tok-s">"POST"</span>, headers: HEADERS,
    body: JSON.stringify({ link_id: linkId })
  });
  <span class="tok-k">const</span> data = <span class="tok-k">await</span> r.json();
  <span class="tok-k">return</span> data.status;
}</pre>
</div></div>
</div></section>

<section id="bot-example"><div class="card">
<h2>Пример бота с проверкой подписки</h2>
<p>Полный рабочий пример Telegram-бота (aiogram 3.x). Пользователь нажимает
«Получить задания» — бот выдаёт спонсоров; после подписки нажимает
«Проверить» — бот вызывает check-resource и сообщает результат.</p>
<div class="code"><div class="body">
<button class="copy" onclick="cp(this)">копировать</button>
<pre class="active"><span class="tok-k">import</span> asyncio
<span class="tok-k">import</span> httpx
<span class="tok-k">from</span> aiogram <span class="tok-k">import</span> Bot, Dispatcher, F
<span class="tok-k">from</span> aiogram.filters <span class="tok-k">import</span> CommandStart
<span class="tok-k">from</span> aiogram.types <span class="tok-k">import</span> (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

BOT_TOKEN = <span class="tok-s">"123456:ABC..."</span>
API = <span class="tok-s">"__BASE__/api/v1"</span>
TOKEN = <span class="tok-s">"fsp_live_xxx"</span>
HEADERS = {<span class="tok-s">"Authorization"</span>: <span class="tok-s">f"Bearer {TOKEN}"</span>}

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


<span class="tok-k">async def</span> <span class="tok-n">api_post</span>(path: str, payload: dict) -> dict:
    <span class="tok-k">async with</span> httpx.AsyncClient(timeout=<span class="tok-n">15</span>) <span class="tok-k">as</span> c:
        r = <span class="tok-k">await</span> c.post(<span class="tok-s">f"{API}{path}"</span>, headers=HEADERS, json=payload)
    <span class="tok-k">return</span> r.json()


<span class="tok-b">@dp.message</span>(CommandStart())
<span class="tok-k">async def</span> <span class="tok-n">start</span>(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=<span class="tok-s">"Получить задания"</span>,
                             callback_data=<span class="tok-s">"get_tasks"</span>)
    ]])
    <span class="tok-k">await</span> message.answer(<span class="tok-s">"Нажмите, чтобы получить задания:"</span>, reply_markup=kb)


<span class="tok-b">@dp.callback_query</span>(F.data == <span class="tok-s">"get_tasks"</span>)
<span class="tok-k">async def</span> <span class="tok-n">get_tasks</span>(cb: CallbackQuery):
    data = <span class="tok-k">await</span> api_post(<span class="tok-s">"/request-op"</span>,
                          {<span class="tok-s">"user_id"</span>: cb.from_user.id, <span class="tok-s">"count"</span>: <span class="tok-n">3</span>})
    <span class="tok-k">if not</span> data.get(<span class="tok-s">"ok"</span>):
        reason = data.get(<span class="tok-s">"reason"</span>)
        <span class="tok-k">if</span> reason == <span class="tok-s">"onboarding_required"</span>:
            <span class="tok-k">await</span> cb.message.answer(
                <span class="tok-s">"Пройдите регистрацию: "</span> + data[<span class="tok-s">"onboarding_url"</span>])
        <span class="tok-k">else</span>:
            <span class="tok-k">await</span> cb.message.answer(<span class="tok-s">"Заданий пока нет."</span>)
        <span class="tok-k">return</span>

    <span class="tok-k">for</span> task <span class="tok-k">in</span> data[<span class="tok-s">"tasks"</span>]:
        link = task.get(<span class="tok-s">"invite_link"</span>) <span class="tok-k">or</span> task.get(<span class="tok-s">"start_link"</span>)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=<span class="tok-s">"Подписаться"</span>, url=link)],
            [InlineKeyboardButton(text=<span class="tok-s">"Проверить"</span>,
                callback_data=<span class="tok-s">f"check:{task['link_id']}"</span>)],
        ])
        <span class="tok-k">await</span> cb.message.answer(
            <span class="tok-s">f"{task['title']} — награда {task['reward_for_publisher']} руб"</span>,
            reply_markup=kb)
    <span class="tok-k">await</span> cb.answer()


<span class="tok-b">@dp.callback_query</span>(F.data.startswith(<span class="tok-s">"check:"</span>))
<span class="tok-k">async def</span> <span class="tok-n">check</span>(cb: CallbackQuery):
    link_id = cb.data.split(<span class="tok-s">":"</span>, <span class="tok-n">1</span>)[<span class="tok-n">1</span>]
    data = <span class="tok-k">await</span> api_post(<span class="tok-s">"/check-resource"</span>, {<span class="tok-s">"link_id"</span>: link_id})
    status = data.get(<span class="tok-s">"status"</span>)
    <span class="tok-k">if</span> status <span class="tok-k">in</span> (<span class="tok-s">"subscribed"</span>, <span class="tok-s">"verified"</span>):
        <span class="tok-k">await</span> cb.answer(<span class="tok-s">"Подписка подтверждена!"</span>, show_alert=<span class="tok-k">True</span>)
    <span class="tok-k">else</span>:
        <span class="tok-k">await</span> cb.answer(<span class="tok-s">"Подписка не найдена. Подпишитесь и повторите."</span>,
                       show_alert=<span class="tok-k">True</span>)


<span class="tok-k">async def</span> <span class="tok-n">main</span>():
    <span class="tok-k">await</span> dp.start_polling(bot)


<span class="tok-k">if</span> __name__ == <span class="tok-s">"__main__"</span>:
    asyncio.run(main())</pre>
</div></div>
<div class="callout"><b>Подсказка:</b> статус <code>subscribed</code> означает, что
юзер подписан (идёт hold-период), <code>verified</code> — подписка подтверждена
и вознаграждение начислено. Оба статуса можно считать успехом для пользователя.</div>
</div></section>

<section id="webhooks"><div class="card">
<h2>Webhooks</h2>
<p>FastSub присылает события об изменении статуса подписок на ваш сервер
(вместо постоянного опроса). Настройка — в боте, раздел Webhook.</p>
<h3>События</h3><table>
<tr><th>Событие</th><th>Когда</th></tr>
<tr><td><code>resource.subscribed</code></td><td>Юзер подписался (hold)</td></tr>
<tr><td><code>resource.verified</code></td><td>Подтверждено, начислено</td></tr>
<tr><td><code>resource.unsubscribed</code></td><td>Юзер отписался</td></tr>
<tr><td><code>resource.expired</code></td><td>TTL вышел без подписки</td></tr>
<tr><td><code>resource.reverted</code></td><td>Финальная отмена после отписки</td></tr>
</table>
<h3>Пример payload</h3><div class="code"><div class="tabs"><div class="tab active" onclick="tab(this,0)">JSON</div></div><div class="body"><button class="copy" onclick="cp(this)">копировать</button><pre class="active">{
  <span class="tok-k">"event"</span>: <span class="tok-s">"resource.verified"</span>,
  <span class="tok-k">"link_id"</span>: <span class="tok-s">"lnk_a1b2c3d4e5f6"</span>,
  <span class="tok-k">"user_id"</span>: <span class="tok-n">123456789</span>,
  <span class="tok-k">"status"</span>: <span class="tok-s">"verified"</span>,
  <span class="tok-k">"reward_rub"</span>: <span class="tok-s">"1.5000"</span>,
  <span class="tok-k">"timestamp"</span>: <span class="tok-s">"2026-05-23T18:04:11Z"</span>
}</pre></div></div>
<h3>Проверка подписи (HMAC-SHA256)</h3>
<p>Каждый запрос содержит <code>X-FastSub-Signature</code>. Проверьте секретом,
выданным при настройке.</p><div class="code"><div class="tabs"><div class="tab active" onclick="tab(this,0)">Python</div><div class="tab" onclick="tab(this,1)">JS</div></div><div class="body"><button class="copy" onclick="cp(this)">копировать</button><pre class="active"><span class="tok-k">import</span> hmac, hashlib

<span class="tok-k">def</span> <span class="tok-n">verify</span>(body, signature, secret):
    expected = hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    <span class="tok-k">return</span> hmac.compare_digest(expected, signature)</pre><pre class=""><span class="tok-k">import</span> crypto <span class="tok-k">from</span> <span class="tok-s">"crypto"</span>;
<span class="tok-k">function</span> <span class="tok-n">verify</span>(body, signature, secret) {
  <span class="tok-k">const</span> expected = crypto
    .createHmac(<span class="tok-s">"sha256"</span>, secret)
    .update(body).digest(<span class="tok-s">"hex"</span>);
  <span class="tok-k">return</span> expected === signature;
}</pre></div></div>
<div class="callout">Заголовки: <code>X-FastSub-Signature</code>,
<code>X-FastSub-Event</code>, <code>X-FastSub-Delivery-Id</code> (идемпотентность).
Отвечайте <b>2xx</b>, иначе доставка повторится с экспоненциальной задержкой.</div>
</div></section>
<section id="errors"><div class="card">
<h2>Коды ошибок</h2>
<h3>HTTP-статусы</h3>
<table>
<tr><th>Код</th><th>detail</th><th>Причина</th></tr>
<tr><td><code>401</code></td><td>missing authorization header</td><td>Нет заголовка Authorization</td></tr>
<tr><td><code>401</code></td><td>invalid authorization scheme</td><td>Ожидается Bearer</td></tr>
<tr><td><code>401</code></td><td>invalid or revoked token</td><td>Токен неверен или отозван</td></tr>
<tr><td><code>401</code></td><td>account disabled</td><td>Аккаунт заблокирован</td></tr>
<tr><td><code>403</code></td><td>belongs to a different publisher</td><td>Чужой link_id</td></tr>
<tr><td><code>404</code></td><td>link_id not found</td><td>Несуществующий link_id</td></tr>
</table>
<h3>reason (в теле при ok=false)</h3>
<table>
<tr><th>reason</th><th>Значение</th></tr>
<tr><td><code>no_tasks</code></td><td>Нет подходящих заданий (в т.ч. не прошли фильтры)</td></tr>
<tr><td><code>onboarding_required</code></td><td>Юзер не прошёл онбординг — покажите onboarding_url</td></tr>
<tr><td><code>bot_disabled</code></td><td>Ваш бот-партнёр отключён</td></tr>
</table>
<div class="callout">Интерактивная схема (OpenAPI) — на <a href="/swagger">/swagger</a>.</div>
</div></section>
  </main>
</div>
<script>
// ripple effect on any button/tab click
function ripple(e,el){
  const r=document.createElement('span');r.className='ripple';
  const rect=el.getBoundingClientRect();
  const size=Math.max(rect.width,rect.height);
  r.style.width=r.style.height=size+'px';
  r.style.left=(e.clientX-rect.left-size/2)+'px';
  r.style.top=(e.clientY-rect.top-size/2)+'px';
  el.appendChild(r);setTimeout(()=>r.remove(),550);
}
function tab(el,i){const c=el.closest('.code');
  c.querySelectorAll('.tab').forEach((t,k)=>t.classList.toggle('active',k===i));
  c.querySelectorAll('.body pre').forEach((p,k)=>p.classList.toggle('active',k===i));}
function cp(btn){const pre=btn.parentElement.querySelector('pre.active')||
  btn.parentElement.querySelector('pre');
  navigator.clipboard.writeText(pre.innerText).then(()=>{
    btn.textContent='скопировано';btn.classList.add('done');
    setTimeout(()=>{btn.textContent='копировать';btn.classList.remove('done')},1500);});}
// attach ripple to tabs and copy buttons, and block text selection on them
document.querySelectorAll('.tab,.copy').forEach(el=>{
  el.addEventListener('click',e=>ripple(e,el));
  el.addEventListener('mousedown',e=>e.preventDefault()); // no text selection
});
// mobile burger menu
const burger=document.getElementById('burger');
const overlay=document.getElementById('overlay');
function closeNav(){document.body.classList.remove('nav-open');}
if(burger){
  burger.addEventListener('click',()=>document.body.classList.toggle('nav-open'));
  overlay.addEventListener('click',closeNav);
  // close menu when a nav link is tapped
  document.querySelectorAll('#nav a').forEach(a=>
    a.addEventListener('click',closeNav));
}
// scroll-spy
const links=[...document.querySelectorAll('#nav a')];
const secs=links.map(a=>document.querySelector(a.getAttribute('href')));
addEventListener('scroll',()=>{let i=secs.length-1;
  for(let k=0;k<secs.length;k++){if(secs[k]&&secs[k].getBoundingClientRect().top>120){i=k-1;break}}
  links.forEach(l=>l.classList.remove('active'));
  if(i>=0&&links[i])links[i].classList.add('active');});
</script>
</body>
</html>"""


@router.get("/docs", include_in_schema=False)
async def custom_docs() -> HTMLResponse:
    return HTMLResponse(_HTML.replace("__BASE__", _BASE_URL))
