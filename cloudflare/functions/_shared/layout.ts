// 全ページ共通のHTML外枠。黒×赤/オレンジのアメリカンスポーツニュース風デザインを踏襲する。
// SEO監査(4-19)で指摘されたH1不足を解消するため、各ページで<h1>を1つだけ明示的に渡す設計にする。

export function renderLayout(opts: {
  pageTitle: string;
  h1: string;
  bodyHtml: string;
  extraHead?: string;
  metaDescription?: string;
}): string {
  const { pageTitle, h1, bodyHtml, extraHead = "", metaDescription = "" } = opts;
  return `<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(pageTitle)}</title>
${metaDescription ? `<meta name="description" content="${escapeHtml(metaDescription)}">` : ""}
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #0d0d0f; color: #e8e8e8; font-family: -apple-system, "Hiragino Sans", "Yu Gothic", sans-serif; }
  header.site-header { background: #16161a; border-bottom: 3px solid #e4002b; padding: 16px 20px; }
  header.site-header a { color: #fff; text-decoration: none; font-weight: 900; font-size: 22px; letter-spacing: 1px; }
  header.site-header a span { color: #e4002b; }
  main { max-width: 900px; margin: 0 auto; padding: 24px 16px; }
  h1 { font-size: 22px; margin: 0 0 20px; border-left: 4px solid #e4002b; padding-left: 10px; }
  .article-card { display: block; background: #18181b; border: 1px solid #2a2a2e; border-radius: 6px; padding: 14px; margin-bottom: 14px; text-decoration: none; color: inherit; }
  .article-card:hover { border-color: #e4002b; }
  .article-card .category-badge { display: inline-block; background: #e4002b; color: #fff; font-size: 11px; padding: 2px 8px; border-radius: 3px; margin-bottom: 8px; }
  .article-card h2 { font-size: 16px; margin: 0 0 6px; }
  .article-card time { font-size: 12px; color: #999; }
  .article-thumbnail { max-width: 100%; width: 100%; height: auto; display: block; border: 1px solid #333; border-radius: 4px; margin-bottom: 16px; }
  .summary-list { padding-left: 20px; line-height: 1.8; }
  .ad-section { margin-top: 20px; padding: 12px 14px; background: #1a1a1c; border-left: 3px solid #ff7a00; }
  .ad-caption { font-size: 11px; color: #ff7a00; font-weight: bold; margin-bottom: 6px; }
  .ad-section a { color: #ffb066; }
  footer.site-footer { text-align: center; padding: 30px 16px; color: #666; font-size: 12px; }
</style>
${extraHead}
</head>
<body>
<header class="site-header">
  <a href="/">Transfer<span>Breaking</span></a>
</header>
<main>
<h1>${escapeHtml(h1)}</h1>
${bodyHtml}
</main>
<footer class="site-footer">&copy; TransferBreaking</footer>
</body>
</html>`;
}

export function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
