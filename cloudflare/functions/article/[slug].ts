import { renderLayout, escapeHtml } from "../_shared/layout";
import { CATEGORY_LABELS, THUMBNAIL_IMAGES, getAdHtml, Article } from "../_shared/config";

interface Env {
  DB: D1Database;
}

export const onRequestGet: PagesFunction<Env> = async (context) => {
  const slug = context.params.slug as string;
  const article = await context.env.DB.prepare("SELECT * FROM articles WHERE slug = ?")
    .bind(slug)
    .first<Article>();

  if (!article) {
    return new Response("Not Found", { status: 404 });
  }

  const label = CATEGORY_LABELS[article.category] ?? CATEGORY_LABELS.OTHER;
  const thumbnail = THUMBNAIL_IMAGES[article.category] ?? THUMBNAIL_IMAGES.OTHER;
  const summaryLines: string[] = JSON.parse(article.summary_lines);
  const sourceName = article.source_name ?? new URL(article.source_url).hostname;

  const summaryHtml = summaryLines.map((line) => `<li>${escapeHtml(line)}</li>`).join("\n");

  const bodyHtml = `
    <img src="${thumbnail}" alt="${escapeHtml(label)}" class="article-thumbnail">
    <span class="category-badge">${escapeHtml(label)}</span>
    <ul class="summary-list">
${summaryHtml}
    </ul>
    <div class="ad-section">
      <div class="ad-caption">ADVERTISEMENT</div>
      ${getAdHtml(article.category)}
    </div>
    <p style="color:#6e6e6e; font-size:11px; margin-top:30px;">
      ※本記事は各情報元の事実データをもとに独自の解説を加えたものです。<br>
      情報元: <a href="${article.source_url}" target="_blank" rel="nofollow noopener" style="color:#8a8a8a;">${escapeHtml(sourceName)}</a>
    </p>`;

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    headline: article.title,
    datePublished: article.published_at,
    dateModified: article.published_at,
    articleSection: label,
  };

  const extraHead = `<script type="application/ld+json">${JSON.stringify(jsonLd)}</script>`;

  const html = renderLayout({
    pageTitle: `${article.title} | TransferBreaking`,
    h1: article.title,
    bodyHtml,
    extraHead,
    metaDescription: summaryLines[0] ?? article.title,
  });

  return new Response(html, {
    headers: { "content-type": "text/html; charset=utf-8" },
  });
};
