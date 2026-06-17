"""Web-form publisher registration.

Stage 3a v2: simplified — no project name, just Telegram username.
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_session
from src.core.db.models import Publisher
from src.core.logging import get_logger
from src.domain.api_tokens import ApiTokenService
from src.domain.publisher_bots import PublisherBotService

router = APIRouter(tags=["public"])
log = get_logger("api.register")


REGISTER_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FastSub — Регистрация партнёра</title>
<style>
:root {
  --bg: #0d1117;
  --card: #161b22;
  --text: #c9d1d9;
  --muted: #8b949e;
  --accent: #2f81f7;
  --accent-hover: #58a6ff;
  --border: #30363d;
  --success: #2ea043;
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  margin: 0; background: var(--bg); color: var(--text);
  min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px;
}
.card { max-width: 480px; width: 100%; background: var(--card);
  border: 1px solid var(--border); border-radius: 12px; padding: 32px; }
h1 { margin: 0 0 8px; font-size: 24px; }
.subtitle { color: var(--muted); margin: 0 0 24px; font-size: 14px; }
label { display: block; font-size: 13px; margin-bottom: 6px; color: var(--muted); }
input[type=text] {
  width: 100%; padding: 10px 14px; background: #0d1117;
  border: 1px solid var(--border); border-radius: 6px; color: var(--text);
  font-size: 15px; margin-bottom: 16px;
}
input[type=text]:focus { outline: none; border-color: var(--accent); }
button {
  width: 100%; padding: 12px; background: var(--accent); color: white;
  border: none; border-radius: 6px; font-size: 15px; font-weight: 600;
  cursor: pointer; transition: background 0.15s;
}
button:hover { background: var(--accent-hover); }
button:disabled { opacity: 0.5; cursor: not-allowed; }
.note { font-size: 12px; color: var(--muted); margin-top: 16px; line-height: 1.5; }
.error { background: rgba(248,81,73,0.1); border: 1px solid rgba(248,81,73,0.3);
  color: #ff7b72; padding: 10px 14px; border-radius: 6px; font-size: 14px; margin-bottom: 16px; }
.success { background: rgba(46,160,67,0.1); border: 1px solid rgba(46,160,67,0.3);
  padding: 16px; border-radius: 6px; margin-bottom: 16px; }
.token-display { font-family: SF Mono, Consolas, monospace; background: #0d1117;
  padding: 12px; border-radius: 6px; word-break: break-all; font-size: 13px;
  margin: 12px 0; border: 1px solid var(--border); }
.copy-hint { font-size: 11px; color: var(--muted); }
a { color: var(--accent); text-decoration: none; } a:hover { text-decoration: underline; }
</style>
</head>
<body>
<div class="card">
<h1>FastSub Партнёры</h1>
<p class="subtitle">Регистрация для разработчиков Telegram-ботов</p>

<div id="error" style="display:none" class="error"></div>
<div id="result" style="display:none"></div>

<form id="reg-form">
<label for="tg_username">Ваш Telegram username</label>
<input type="text" id="tg_username" name="tg_username" required pattern="^@?[a-zA-Z][a-zA-Z0-9_]{3,31}$" placeholder="@yourname">

<label for="bot_name">Название первого бота</label>
<input type="text" id="bot_name" name="bot_name" required minlength="2" maxlength="128" placeholder="Cinema Bot">

<button type="submit" id="submit-btn">Получить API-ключ</button>

<p class="note">
После регистрации <b>обязательно</b> откройте бот
<a href="https://t.me/fastsub_publisher_bot">@fastsub_publisher_bot</a>
и нажмите <code>/start</code>, чтобы подтвердить владение аккаунтом.
</p>
</form>
</div>

<script>
const form = document.getElementById('reg-form');
const errBox = document.getElementById('error');
const resultBox = document.getElementById('result');
const submitBtn = document.getElementById('submit-btn');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  errBox.style.display = 'none';
  submitBtn.disabled = true;
  submitBtn.textContent = 'Создаю...';

  const fd = new FormData(form);
  try {
    const resp = await fetch('/register', { method: 'POST', body: fd });
    const data = await resp.json();
    if (!resp.ok) {
      errBox.textContent = data.detail || 'Ошибка регистрации';
      errBox.style.display = 'block';
      submitBtn.disabled = false;
      submitBtn.textContent = 'Получить API-ключ';
      return;
    }
    form.style.display = 'none';
    resultBox.innerHTML = `
      <div class="success">
        <strong>✓ Регистрация успешна!</strong>
        <p style="margin: 8px 0 0; font-size:13px;">Ваш API-токен (показывается один раз):</p>
        <div class="token-display">${data.token}</div>
        <p class="copy-hint">Используйте: <code>Authorization: Bearer ${data.token.substring(0, 20)}...</code></p>
      </div>
      <p class="note">
        <b>Следующий шаг:</b> откройте <a href="https://t.me/fastsub_publisher_bot">@fastsub_publisher_bot</a> и нажмите <code>/start</code>.
      </p>
    `;
    resultBox.style.display = 'block';
  } catch (err) {
    errBox.textContent = 'Сеть недоступна. Попробуйте позже.';
    errBox.style.display = 'block';
    submitBtn.disabled = false;
    submitBtn.textContent = 'Получить API-ключ';
  }
});
</script>
</body>
</html>
"""


@router.get("/register", response_class=HTMLResponse)
async def register_form() -> HTMLResponse:
    return HTMLResponse(content=REGISTER_HTML)


@router.post("/register")
async def register_submit(
    tg_username: str = Form(..., min_length=5, max_length=32),
    bot_name: str = Form(..., min_length=2, max_length=128),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Create a publisher + first PublisherBot + API token via web form.

    Stage 3a v2: TG identity is provisional (placeholder negative id).
    User must /start the bot to "claim" the account properly.
    """
    clean_username = tg_username.strip().lstrip("@")

    try:
        clean_name = PublisherBotService.validate_name(bot_name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    # Check uniqueness of TG username
    result = await session.execute(
        select(Publisher).where(Publisher.tg_username == clean_username)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Юзернейм @{clean_username} уже зарегистрирован. "
                   f"Откройте @fastsub_publisher_bot чтобы войти.",
        )

    # Placeholder TG ID (negative, hash-based)
    placeholder_tg_id = -abs(
        int(hashlib.sha256(clean_username.encode()).hexdigest()[:12], 16)
    ) % (10**18)

    publisher = Publisher(
        tg_user_id=placeholder_tg_id,
        tg_username=clean_username,
        full_name=None,
        project_name="Default",
    )
    session.add(publisher)
    await session.flush()

    # Create first PublisherBot (no TG token — just a name)
    bot_svc = PublisherBotService(session)
    pub_bot = await bot_svc.add_bot(publisher_id=publisher.id, name=clean_name)

    # First API token bound to this bot
    tok_svc = ApiTokenService(session)
    token_result = await tok_svc.create_for_bot(
        publisher_id=publisher.id,
        publisher_bot_id=pub_bot.id,
        label="Web-registration",
    )

    log.info("publisher_registered_web",
             publisher_id=publisher.id, username=clean_username, bot_id=pub_bot.id)

    return JSONResponse({
        "ok": True,
        "publisher_id": publisher.id,
        "publisher_bot_id": pub_bot.id,
        "token": token_result.plaintext,
    })
