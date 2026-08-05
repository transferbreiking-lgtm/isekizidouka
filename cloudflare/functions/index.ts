import { renderLayout, escapeHtml } from "./_shared/layout";
import { CATEGORY_LABELS, Article } from "./_shared/config";

interface Env {
  DB: D1Database;
}

export const onRequestGet: PagesFunction<Env> = async (context) => {
  const { results } = await context.env.DB.prepare(
    "SELECT * FROM articles ORDER BY published_at DESC LIMIT 20"
  ).all<Article>();

  const cards = (results ?? [])
    .map((a) => {
      const label = CATEGORY_LABELS[a.category] ?? CATEGORY_LABELS.OTHER;
      return `<a class="article-card" href="/article/${encodeURIComponent(a.slug)}">
        <span class="category-badge">${escapeHtml(label)}</span>
        <h2>${escapeHtml(a.title)}</h2>
        <time>${escapeHtml(a.published_at)}</time>
      </a>`;
    })
    .join("\n");

  const bodyHtml =
    (results ?? []).length > 0
      ? cards
      : `<p style="color:#999;">まだ記事がありません(移行作業中のテストページです)。</p>`;

  const html = renderLayout({
    pageTitle: "TransferBreaking - 世界のプロスポーツ移籍情報",
    h1: "最新の移籍ニュース",
    bodyHtml,
  });

  return new Response(html, {
    headers: { "content-type": "text/html; charset=utf-8" },
  });
};
