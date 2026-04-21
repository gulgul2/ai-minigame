-- Supabase에서 실행할 SQL
-- Table Editor > New Table 대신 SQL Editor에서 실행

CREATE TABLE scores (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  game_date DATE NOT NULL,
  nickname TEXT NOT NULL CHECK (nickname IN ('태형', '상이', '세준', '영근')),
  score INTEGER NOT NULL CHECK (score >= 0),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 인덱스 (날짜별 리더보드 조회 최적화)
CREATE INDEX idx_scores_game_date ON scores (game_date, score DESC);

-- RLS 활성화 (필수!)
ALTER TABLE scores ENABLE ROW LEVEL SECURITY;

-- 읽기: 누구나 가능
CREATE POLICY "scores_select" ON scores
  FOR SELECT USING (true);

-- 쓰기: 닉네임 4개만, 오늘 날짜만 허용
CREATE POLICY "scores_insert" ON scores
  FOR INSERT WITH CHECK (
    nickname IN ('태형', '상이', '세준', '영근')
    AND game_date = CURRENT_DATE
    AND score >= 0
  );

-- 수정/삭제 불가 (정책 없음 = 거부)
