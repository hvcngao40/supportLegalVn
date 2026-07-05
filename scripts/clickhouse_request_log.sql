CREATE TABLE IF NOT EXISTS request_log (
  log_id String,
  request_id String,
  phase Enum8('request' = 1, 'response' = 2),
  user_id String,
  method LowCardinality(String),
  route LowCardinality(String),
  path String,
  status_code UInt16,
  success UInt8,
  event_code LowCardinality(String),
  event_instance_id String,
  occurred_at DateTime64(3, 'Asia/Ho_Chi_Minh'),
  period_day Date,
  latency_ms UInt32,
  meta JSON
)
ENGINE = MergeTree
ORDER BY (period_day, event_code, user_id, occurred_at)
PARTITION BY toYYYYMM(occurred_at)
TTL toDateTime(occurred_at) + INTERVAL 12 MONTH;

-- Smoke checks after one request:
-- SELECT count() FROM request_log;
-- SELECT countDistinct(event_instance_id) FROM request_log WHERE event_code != '';
