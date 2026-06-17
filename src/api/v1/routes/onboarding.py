"""Onboarding web-form for end users.

Two routes:
  - GET  /onboard/{token} — render HTML form (no auth, token is the secret)
  - POST /onboard/{token} — handle form submission, create EndUser

The token is one-shot: consumed (deleted from Redis) on successful POST.
On invalid/expired token — show a friendly error page.
"""

from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_session
from src.core.logging import get_logger
from src.domain.end_users import EndUserService, OnboardingTokenService
from src.domain.exceptions import DomainError

# No prefix — this is a top-level page, not under /api/v1
router = APIRouter(tags=["onboarding"])
log = get_logger("api.onboarding")


# --- HTML templates ---


def _render_form(token: str) -> str:
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>FastSub — Регистрация</title>
<style>
  :root {{
    --bg: #0d1117;
    --panel: #161b22;
    --border: #30363d;
    --text: #e6edf3;
    --muted: #7d8590;
    --accent: #2f81f7;
    --accent-hover: #1f6feb;
    --success: #238636;
    --error: #f85149;
    --radius: 8px;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    margin: 0;
    padding: 0;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
  }}
  .wrap {{
    max-width: 480px;
    margin: 0 auto;
    padding: 28px 20px 60px;
  }}
  h1 {{
    font-size: 22px;
    font-weight: 600;
    margin: 0 0 8px;
  }}
  .lead {{
    color: var(--muted);
    font-size: 14px;
    margin: 0 0 24px;
    line-height: 1.5;
  }}
  form {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
  }}
  .field {{ margin-bottom: 18px; }}
  label.label {{
    display: block;
    font-weight: 500;
    font-size: 14px;
    margin-bottom: 8px;
  }}
  .options {{
    display: flex;
    flex-direction: column;
    gap: 8px;
  }}
  .options.row {{
    flex-direction: row;
    flex-wrap: wrap;
    gap: 6px;
  }}
  .opt {{
    display: flex;
    align-items: center;
    padding: 10px 12px;
    background: #0d1117;
    border: 1px solid var(--border);
    border-radius: 6px;
    cursor: pointer;
    transition: border-color 0.1s, background 0.1s;
    font-size: 14px;
    user-select: none;
  }}
  .opt:hover {{ border-color: #58a6ff; }}
  .opt input[type="radio"] {{
    margin-right: 8px;
    accent-color: var(--accent);
  }}
  .opt.selected {{
    border-color: var(--accent);
    background: rgba(47, 129, 247, 0.08);
  }}
  .options.row .opt {{ flex: 1 0 calc(50% - 6px); }}
  input[type="text"] {{
    width: 100%;
    background: #0d1117;
    border: 1px solid var(--border);
    color: var(--text);
    font-size: 14px;
    padding: 10px 12px;
    border-radius: 6px;
    outline: none;
  }}
  input[type="text"]:focus {{ border-color: var(--accent); }}
  .consent {{
    display: flex;
    gap: 10px;
    align-items: flex-start;
    font-size: 13px;
    color: var(--muted);
    line-height: 1.5;
    margin-top: 8px;
  }}
  .consent input[type="checkbox"] {{
    margin-top: 2px;
    accent-color: var(--accent);
  }}
  button[type="submit"] {{
    width: 100%;
    padding: 12px;
    background: var(--success);
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.1s;
    margin-top: 10px;
  }}
  button[type="submit"]:hover {{ background: #2ea043; }}
  button[type="submit"]:disabled {{
    background: #2d333b;
    cursor: not-allowed;
    color: var(--muted);
  }}
  .other-input {{
    margin-top: 8px;
    display: none;
  }}
  .other-input.show {{ display: block; }}
  footer {{
    margin-top: 20px;
    text-align: center;
    color: var(--muted);
    font-size: 12px;
  }}
</style>
</head>
<body>
<div class="wrap">
  <h1>🚀 FastSub</h1>
  <p class="lead">Заполните короткую анкету, чтобы получать персонализированные задания. Все поля можно пропустить.</p>

  <form method="post" action="/onboard/{escape(token)}" id="onb-form">

    <div class="field">
      <label class="label">Возраст</label>
      <div class="options">
        <label class="opt"><input type="radio" name="age_range" value="under_14"> Младше 14 лет</label>
        <label class="opt"><input type="radio" name="age_range" value="14_16"> 14 – 16 лет</label>
        <label class="opt"><input type="radio" name="age_range" value="16_18"> 16 – 18 лет</label>
        <label class="opt"><input type="radio" name="age_range" value="18_plus"> 18 лет и старше</label>
      </div>
    </div>

    <div class="field">
      <label class="label">Пол</label>
      <div class="options row">
        <label class="opt"><input type="radio" name="gender" value="male"> Мужской</label>
        <label class="opt"><input type="radio" name="gender" value="female"> Женский</label>
        <label class="opt"><input type="radio" name="gender" value="undisclosed"> Не указывать</label>
      </div>
    </div>

    <div class="field">
      <label class="label">Страна</label>
      <div class="options">
        <label class="opt"><input type="radio" name="country_code" value="RU"> 🇷🇺 Россия</label>
        <label class="opt"><input type="radio" name="country_code" value="UA"> 🇺🇦 Украина</label>
        <label class="opt"><input type="radio" name="country_code" value="BY"> 🇧🇾 Беларусь</label>
        <label class="opt"><input type="radio" name="country_code" value="KZ"> 🇰🇿 Казахстан</label>
        <label class="opt"><input type="radio" name="country_code" value="OTHER"> 🌍 Другая</label>
      </div>
      <div class="other-input" id="other-input">
        <input type="text" name="country_other" placeholder="Введите название страны" maxlength="64">
      </div>
    </div>

    <div class="consent">
      <input type="checkbox" name="consent" id="consent" required>
      <label for="consent">Я согласен(на) на обработку моих данных согласно политике конфиденциальности FastSub.</label>
    </div>

    <button type="submit" id="submit-btn">Завершить регистрацию</button>
  </form>

  <footer>FastSub © 2026</footer>
</div>

<script>
  // Highlight selected radio options
  document.querySelectorAll('input[type="radio"]').forEach(input => {{
    input.addEventListener('change', () => {{
      const name = input.name;
      document.querySelectorAll(`input[name="${{name}}"]`).forEach(other => {{
        other.closest('.opt').classList.toggle('selected', other.checked);
      }});
      if (name === 'country_code') {{
        const otherDiv = document.getElementById('other-input');
        if (input.value === 'OTHER' && input.checked) {{
          otherDiv.classList.add('show');
        }} else {{
          otherDiv.classList.remove('show');
        }}
      }}
    }});
  }});
</script>
</body>
</html>
"""


def _render_error(title: str, message: str) -> str:
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FastSub — Ошибка</title>
<style>
  body {{
    background: #0d1117;
    color: #e6edf3;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 0;
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    padding: 20px;
  }}
  .box {{
    max-width: 420px;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 30px;
    text-align: center;
  }}
  h1 {{ margin: 0 0 14px; font-size: 22px; }}
  p {{ margin: 0; color: #7d8590; line-height: 1.5; }}
  .icon {{ font-size: 48px; margin-bottom: 12px; }}
</style>
</head>
<body>
<div class="box">
  <div class="icon">⚠️</div>
  <h1>{escape(title)}</h1>
  <p>{escape(message)}</p>
</div>
</body>
</html>
"""


def _render_success() -> str:
    return """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FastSub — Готово</title>
<style>
  body {
    background: #0d1117;
    color: #e6edf3;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 0;
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    padding: 20px;
  }
  .box {
    max-width: 420px;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 30px;
    text-align: center;
  }
  h1 { margin: 0 0 14px; font-size: 24px; color: #3fb950; }
  p { margin: 0; color: #7d8590; line-height: 1.5; }
  .icon { font-size: 56px; margin-bottom: 16px; }
</style>
</head>
<body>
<div class="box">
  <div class="icon">✅</div>
  <h1>Регистрация завершена!</h1>
  <p>Вернитесь в Telegram-бот и нажмите <b>/start</b> ещё раз, чтобы получить задания.</p>
</div>
</body>
</html>
"""


# --- Routes ---


@router.get("/onboard/{token}", response_class=HTMLResponse, include_in_schema=False)
async def show_form(token: str) -> HTMLResponse:
    """Render onboarding form. Token validated for existence only."""
    token_svc = OnboardingTokenService()
    payload = await token_svc.resolve(token)
    if payload is None:
        return HTMLResponse(
            _render_error(
                "Ссылка устарела",
                "Эта ссылка для регистрации больше не действительна. "
                "Запросите новую в боте, отправив /start.",
            ),
            status_code=404,
        )
    return HTMLResponse(_render_form(token))


@router.post("/onboard/{token}", response_class=HTMLResponse, include_in_schema=False)
async def submit_form(
    token: str,
    request: Request,
    age_range: str | None = Form(default=None),
    gender: str | None = Form(default=None),
    country_code: str | None = Form(default=None),
    country_other: str | None = Form(default=None),
    consent: str | None = Form(default=None),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Submit handler — validate, create EndUser, consume token."""
    if not consent:
        return HTMLResponse(
            _render_error(
                "Не дано согласие",
                "Чтобы продолжить, нужно поставить галочку согласия.",
            ),
            status_code=400,
        )

    token_svc = OnboardingTokenService()
    payload = await token_svc.resolve(token)
    if payload is None:
        return HTMLResponse(
            _render_error(
                "Ссылка устарела",
                "Эта ссылка для регистрации больше не действительна.",
            ),
            status_code=404,
        )

    # Normalize empty strings to None
    age_range = age_range or None
    gender = gender or None
    country_code = country_code or None
    country_other = (country_other or "").strip() or None

    svc = EndUserService(session)
    try:
        end_user = await svc.create_from_form(
            user_tg_id=payload.user_tg_id,
            gender=gender,
            age_range=age_range,
            country_code=country_code,
            country_other=country_other,
            publisher_bot_id=payload.publisher_bot_id,
        )
    except DomainError as e:
        return HTMLResponse(
            _render_error("Ошибка валидации", str(e)),
            status_code=400,
        )

    # Consume token (one-shot)
    await token_svc.consume(token)

    log.info(
        "end_user_onboarded",
        user_tg_id=end_user.user_tg_id,
        country=end_user.country_code,
        age=end_user.age_range,
    )

    return HTMLResponse(_render_success())
