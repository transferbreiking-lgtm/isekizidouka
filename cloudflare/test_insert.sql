INSERT INTO articles (slug, category, player_name, team_name, title, summary_lines, source_url, source_url_normalized, source_name, published_at)
VALUES (
  'test-migration-check-001',
  'SOCCER',
  'テスト選手',
  '日本代表',
  '【動作確認】Cloudflare移行テスト記事',
  '["これはCloudflare移行の動作確認用テスト記事です。","D1からPages Functionsで正常に表示されるかを確認しています。","本番記事ではありません。"]',
  'https://example.com/test-article',
  'https://example.com/test-article',
  'Example News',
  '2026-08-04T00:00:00+09:00'
);
