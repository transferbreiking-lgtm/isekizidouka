-- TransferBreaking: Cloudflare D1 記事テーブル定義
-- main.pyのparse_ai_output()が出力する項目(category, player_name, team_name, title, summary_lines)と
-- send_to_blog()が投稿時に扱っていたsource_url等を保持する。summary_linesはJSON配列文字列で保存する。

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    player_name TEXT,
    team_name TEXT,
    title TEXT NOT NULL,
    summary_lines TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_url_normalized TEXT NOT NULL,
    source_name TEXT,
    published_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- main.pyの重複防止ロジック(4-22: 正規化URL比較)に合わせたユニーク制約
CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_source_url_normalized ON articles (source_url_normalized);

-- 一覧・カテゴリアーカイブ・チームアーカイブでの絞り込みに使う想定のインデックス
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles (category);
CREATE INDEX IF NOT EXISTS idx_articles_team_name ON articles (team_name);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles (published_at DESC);
