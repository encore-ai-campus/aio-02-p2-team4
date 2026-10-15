ALTER TABLE conversations ADD COLUMN IF NOT EXISTS expires_at timestamptz;

-- 이전 기록에는 세션 발급 시각이 없으므로 소유자의 첫 대화 생성일을 기준으로 이관합니다.
WITH deadlines AS (
  SELECT owner_id, min(created_at) + interval '30 days' AS expires_at
  FROM conversations
  GROUP BY owner_id
)
UPDATE conversations AS conversation
SET expires_at = deadlines.expires_at
FROM deadlines
WHERE conversation.owner_id = deadlines.owner_id AND conversation.expires_at IS NULL;

ALTER TABLE conversations ALTER COLUMN expires_at SET NOT NULL;
CREATE INDEX IF NOT EXISTS conversations_expiry ON conversations(expires_at);
