CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS campaign (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  starts_at timestamptz NOT NULL DEFAULT now(),
  ends_at timestamptz NOT NULL DEFAULT (now() + interval '10 years'),
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mission (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id uuid NOT NULL REFERENCES campaign(id),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  period_type text NOT NULL CHECK (period_type IN ('daily', 'weekly')),
  is_active boolean NOT NULL DEFAULT true,
  sort_order integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  route text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event_mission (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mission_id uuid NOT NULL REFERENCES mission(id),
  event_id uuid NULL REFERENCES event(id),
  target integer NOT NULL DEFAULT 1,
  points integer NOT NULL DEFAULT 0,
  sort_order integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE event_mission
  ADD COLUMN IF NOT EXISTS rule_type text NOT NULL DEFAULT 'count',
  ADD COLUMN IF NOT EXISTS event_codes text[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS config jsonb NOT NULL DEFAULT '{}';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'event_mission_rule_type_check'
      AND conrelid = 'event_mission'::regclass
  ) THEN
    ALTER TABLE event_mission
      ADD CONSTRAINT event_mission_rule_type_check
      CHECK (rule_type IN ('count', 'distinct_days', 'streak', 'meta_mission'));
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'event_mission_mission_sort_unique'
      AND conrelid = 'event_mission'::regclass
  ) THEN
    ALTER TABLE event_mission
      ADD CONSTRAINT event_mission_mission_sort_unique
      UNIQUE (mission_id, sort_order);
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS user_progress (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  event_mission_id uuid NOT NULL REFERENCES event_mission(id),
  mission_id uuid NOT NULL REFERENCES mission(id),
  period_key text NOT NULL,
  progress integer NOT NULL DEFAULT 0,
  target integer NOT NULL,
  status text NOT NULL DEFAULT 'in_progress'
    CHECK (status IN ('in_progress', 'completed')),
  points_awarded integer NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, event_mission_id, period_key)
);

CREATE INDEX IF NOT EXISTS idx_up_mission_period
  ON user_progress (mission_id, period_key);

CREATE TABLE IF NOT EXISTS user_point (
  user_id uuid PRIMARY KEY REFERENCES users(id),
  total_points integer NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_point_weekly (
  user_id uuid NOT NULL REFERENCES users(id),
  period_key text NOT NULL,
  points integer NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, period_key)
);

WITH upsert_campaign AS (
  INSERT INTO campaign (code, name, starts_at, ends_at, is_active)
  VALUES ('gamification_mvp', 'Gamification MVP', now() - interval '1 day', now() + interval '10 years', true)
  ON CONFLICT (code) DO UPDATE
    SET name = EXCLUDED.name,
        starts_at = EXCLUDED.starts_at,
        ends_at = EXCLUDED.ends_at,
        is_active = EXCLUDED.is_active
  RETURNING id
),
campaign_row AS (
  SELECT id FROM upsert_campaign
  UNION ALL
  SELECT id FROM campaign WHERE code = 'gamification_mvp'
  LIMIT 1
),
events AS (
  INSERT INTO event (code, name, route)
  VALUES
    ('prompt_sent', 'Gửi câu hỏi', '/chat/prompt'),
    ('upload_doc', 'Tải tài liệu', '/documents/upload'),
    ('summarize', 'Tóm tắt tài liệu', '/documents/summarize'),
    ('find_key_points', 'Tìm ý chính', '/documents/key-points')
  ON CONFLICT (code) DO UPDATE
    SET name = EXCLUDED.name,
        route = EXCLUDED.route
  RETURNING code
),
daily AS (
  INSERT INTO mission (campaign_id, code, name, period_type, sort_order)
  SELECT id, 'daily_core_actions', 'Hoàn thành nhiệm vụ hằng ngày', 'daily', 10
  FROM campaign_row
  ON CONFLICT (code) DO UPDATE
    SET name = EXCLUDED.name,
        period_type = EXCLUDED.period_type,
        sort_order = EXCLUDED.sort_order
  RETURNING id
),
weekly AS (
  INSERT INTO mission (campaign_id, code, name, period_type, sort_order)
  SELECT id, 'weekly_daily_finisher', 'Duy trì hoàn thành nhiệm vụ ngày', 'weekly', 20
  FROM campaign_row
  ON CONFLICT (code) DO UPDATE
    SET name = EXCLUDED.name,
        period_type = EXCLUDED.period_type,
        sort_order = EXCLUDED.sort_order
  RETURNING id
)
INSERT INTO event_mission (mission_id, target, points, sort_order, rule_type, event_codes, config)
SELECT id, 4, 40, 10, 'count', ARRAY['prompt_sent', 'upload_doc', 'summarize', 'find_key_points'], '{"event_codes":["prompt_sent","upload_doc","summarize","find_key_points"]}'::jsonb
FROM daily
UNION ALL
SELECT id, 4, 120, 20, 'meta_mission', ARRAY[]::text[], '{"source_mission_codes":["daily_core_actions"]}'::jsonb
FROM weekly
ON CONFLICT (mission_id, sort_order) DO UPDATE
  SET target = EXCLUDED.target,
      points = EXCLUDED.points,
      rule_type = EXCLUDED.rule_type,
      event_codes = EXCLUDED.event_codes,
      config = EXCLUDED.config;
