# FastSub — архитектура

Этот документ описывает зафиксированные решения. Когда что-то меняется
в обсуждении — обновляем здесь, чтобы новые этапы опирались на актуальное.

## Роли

- **Advertiser** (рекламодатель): создаёт кампании, пополняет баланс через CryptoBot
- **Publisher** (паблишер): владеет ботом, дёргает наш API, получает выплаты
- **Admin**: модерирует кампании, видит статистику, делает ручные операции
- **End user**: конечный юзер бота паблишера, выполняет задания (подписки)

## Поток данных (happy path)

```
1. Advertiser создаёт кампанию в advertiser-боте
   → Campaign(DRAFT)
   → CampaignResource(PENDING) для каждого канала/бота

2. Advertiser пополняет баланс через CryptoBot
   → CryptoBot webhook → Transaction(advertiser_topup, COMPLETED)
   → advertiser.balance_rub += amount_rub (с конверсией крипты)

3. Advertiser оплачивает кампанию
   → advertiser.balance_rub -= budget_total → advertiser.reserved_rub +=
   → Campaign(PENDING_MODERATION)

4. Admin модерирует
   → Campaign(ACTIVE)
   → Checker-бот создаёт invite_link для каждого ресурса
   → CampaignResource(ACTIVE)

5. Publisher запрашивает задание для своего юзера
   POST /api/v1/request-op
     body: { user_id, user_context: {premium, lang, ...}, count: 3 }
   → выбираем ресурсы с учётом таргетинга, дедупа по истории юзера
   → создаём task_id + N × ResourceIssue(PENDING) с link_id
   → резервируем budget на campaign (campaign.budget_reserved += reward)

6. Юзер подписывается по invite_link
   → checker-бот получает chat_member update
   → находим resource_issue по (user_tg_id, campaign_resource_id, publisher_id)
   → ResourceIssue(SUBSCRIBED), subscribed_at = now()
   → hold_until = now() + dynamic_hold_hours(publisher.retention_rate)
   → инкремент campaign_resource.actual_subscribers
   → webhook → publisher: resource.subscribed

7. Publisher проверяет
   POST /api/v1/check-resource { link_id }
   → возвращаем текущий статус (SUBSCRIBED, ещё в hold)

8. Worker (каждые 15 минут) проверяет hold_until <= now()
   → для каждого SUBSCRIBED делает getChatMember (свежая проверка)
   → если всё ок: ResourceIssue(VERIFIED), верифицируем
     - publisher.hold_rub += payout
     - publisher.balance_rub += payout (мгновенно, т.к. hold уже прошёл)
     - actually we keep them separate? см. ниже
     - Transaction(publisher_earn) + Transaction(platform_commission)
     - Transaction(campaign_spend): campaign.budget_spent +=, reserved -=
     - webhook → publisher: resource.verified

9. Если юзер отписался ДО hold_until:
   → checker-бот получает chat_member(left)
   → ResourceIssue(UNSUBSCRIBED)
   → если уже была SUBSCRIBED но не VERIFIED — никаких финансовых операций,
     просто отменяем (бюджет вернётся в campaign)
   → актуализируем retention_rate паблишера
   → webhook → publisher: resource.unsubscribed

10. Если link_id истёк (expires_at < now() и status=PENDING):
    → ResourceIssue(EXPIRED)
    → возвращаем бронь в кампанию (budget_reserved -= reward)
```

## Финансовая модель

### Balances

**Advertiser:**
- `balance_rub` — свободные деньги, можно тратить
- `reserved_rub` — забронированы под активные кампании
- `total_spent_rub` — суммарно списано (для статистики)

**Publisher:**
- `balance_rub` — доступные к выводу
- `hold_rub` — в hold (заработаны, но ещё не верифицированы)
- `total_earned_rub`, `total_paid_out_rub`

### Round-trip одной подписки

При выдаче (`/request-op`):
- `campaign.budget_reserved += reward` (бронь)

При верификации (`VERIFIED`):
- `campaign.budget_reserved -= reward`
- `campaign.budget_spent += reward`
- `publisher.hold_rub -= payout` (если до этого начисляли в hold) или сразу:
- `publisher.balance_rub += payout`
- Запись Transaction'ов: `publisher_earn`, `platform_commission`, `campaign_spend`

При отписке (`UNSUBSCRIBED → REVERTED`):
- Если уже было VERIFIED: списываем с `publisher.balance_rub`, возвращаем `advertiser.balance_rub`
  (на практике — возвращаем в `campaign.budget_reserved` чтобы крутить дальше; деньги остаются у нас, advertiser не получает обратно деньги пока кампания не остановлена)
- Если было только SUBSCRIBED: возвращаем бронь
- Учитываем в `publisher.total_unsubscriptions` для retention

### Округление

- Хранение: `NUMERIC(18, 4)` — 4 знака
- Отображение: 2 знака, `ROUND_HALF_UP`
- Никогда `float`. Конверсия `float → str → Decimal`.

### Конверсия крипты → рубли

В момент создания CryptoBot инвойса:
1. Запрашиваем курс из CoinGecko/Binance (кэш 5 минут)
2. Фиксируем `rate` в `transactions.meta.exchange_rate`
3. `amount_rub = amount_crypto * rate` (округляем до 4 знаков)
4. После оплаты — пополняем `balance_rub` уже в рублях

## Динамический hold-период

```python
def compute_hold_hours(publisher: Publisher) -> int:
    # Cold start
    if publisher.verified_subs_in_window < COLD_START_MIN_SUBS:
        return COLD_START_HOLD_HOURS  # 8
    rate = publisher.retention_rate
    if rate >= 80: return 4
    if rate >= 50: return 6
    if rate >= 40: return 8
    return 12
```

**`retention_rate`** = доля подписок старше 4 часов из всех проверенных
за окно 7 дней. Пересчитывается:
- При каждом verified-событии (инкрементально через triggers или в коде)
- Раз в сутки полным пересчётом (cleanup ошибок)

## Retention-бонус

Если `publisher.retention_rate >= 90` И `verified_subs_in_window >= COLD_START_MIN_SUBS`:
- Дополнительно начисляем `5%` от payout как `PUBLISHER_BONUS`
- Бонус выплачивается за счёт **платформы** (из её части комиссии)
- Снимается с следующей подписки, если retention упал ниже порога

## Overflow при заполнении кампании

Сценарий: target_subscribers=1000, актуально 998, выдано 5 link_id одновременно.

1. Все 5 link_id выдаются (бронь по 5 reward'ам)
2. Все 5 юзеров успели подписаться
3. Первые 2 — VERIFIED как обычно (998→999→1000)
4. Оставшиеся 3 — `actual_subscribers >= target_subscribers`, помечаем ResourceIssue как INVALID с reason="already_full"
5. Бронь по INVALID issue возвращается в campaign (если ещё есть activе ресурсы) или в advertiser.balance_rub
6. Webhook паблишеру: `resource.expired` с reason

CampaignResource → COMPLETED. Если все ресурсы кампании COMPLETED → Campaign(COMPLETED).

## API-схема (черновик для этапа 3)

```
POST /api/v1/request-op
  Auth: Bearer fs_<token>
  Body: { user_id, user_context, count=1, exclude_link_ids=[] }
  → { task_id, resources: [{ link_id, type, title, join_url, reward_rub, ... }] }

POST /api/v1/check-resource
  Body: { link_id }
  → { link_id, status, subscribed_at, verified_at, payout_rub, ... }

POST /api/v1/check-task
  Body: { task_id }
  → { task_id, resources: [...] }

GET /api/v1/user/{user_id}/history?limit=50&before=...
  → { items: [{ link_id, resource: {...}, status, timestamps }] }

GET /api/v1/user/{user_id}/subscriptions
  → активные подписки юзера (для дедупа в /request-op)

GET /api/v1/resource/{link_id}
  → детальная инфа

GET /api/v1/balance
  → { balance_rub, hold_rub, retention_rate, hold_hours }

GET /api/v1/stats?from=...&to=...
  → счётчики

POST /api/v1/webhook/configure
  Body: { url, events?: ["resource.subscribed", ...] }
  → { secret }   # вернётся один раз

POST /webhook/cryptobot       # для входящего webhook от CryptoBot
```

## Идемпотентность

- `/check-resource` идемпотентен: возвращает текущий статус, ничего не меняет
- `Transaction.idempotency_key` гарантирует, что повторные попытки записи
  одной операции (например, retry CryptoBot webhook) не создадут дубликат
- `ResourceIssue.link_id` уникален → повторная выдача невозможна

## Партиционирование

`verification_logs` — by RANGE(created_at), помесячно. Партиции создаём
заранее (worker раз в сутки создаёт партицию на 2 месяца вперёд).
Старые партиции (>90 дней) можно DETACH + хранить отдельно или DROP.

## Где что искать

- `src/core/db/models/` — описание схемы (всегда актуально, ORM)
- `migrations/versions/` — версионирование схемы
- `src/core/db/models/enums.py` — все enum-ы системы
- `src/shared/money.py` — все денежные расчёты
- `docs/` — концептуальная документация (этот файл)
