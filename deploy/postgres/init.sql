-- Включаем нужные расширения
CREATE EXTENSION IF NOT EXISTS pgcrypto;     -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- поиск по тексту
CREATE EXTENSION IF NOT EXISTS btree_gin;    -- индексы для JSONB

-- Базовые настройки
ALTER DATABASE fastsub SET timezone TO 'UTC';
