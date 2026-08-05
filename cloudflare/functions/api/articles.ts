// main.py(GitHub Actions)からの記事投稿を受け付けるエンドポイント。
// POST /api/articles
// 認証: X-Ingest-Secret ヘッダーをCloudflare Pages側の環境変数 INGEST_SECRET と比較する。
// LivedoorのAtomPub投稿(send_to_blog)の代わりに、この後main.py側から呼び出す想定。

interface Env {
  DB: D1Database;
  INGEST_SECRET: string;
}

interface ArticlePayload {
  slug: string;
  category: string;
  player_name?: string | null;
  team_name?: string | null;
  title: string;
  summary_lines: string[];
  source_url: string;
  source_url_normalized: string;
  source_name?: string | null;
  published_at: string;
}

export const onRequestPost: PagesFunction<Env> = async (context) => {
  const secret = context.request.headers.get("X-Ingest-Secret");
  if (!secret || secret !== context.env.INGEST_SECRET) {
    return new Response(JSON.stringify({ error: "unauthorized" }), {
      status: 401,
      headers: { "content-type": "application/json" },
    });
  }

  let payload: ArticlePayload;
  try {
    payload = await context.request.json();
  } catch {
    return new Response(JSON.stringify({ error: "invalid json" }), {
      status: 400,
      headers: { "content-type": "application/json" },
    });
  }

  const required = ["slug", "category", "title", "summary_lines", "source_url", "source_url_normalized", "published_at"];
  for (const key of required) {
    if (!(key in payload) || (payload as any)[key] === undefined || (payload as any)[key] === null) {
      return new Response(JSON.stringify({ error: `missing field: ${key}` }), {
        status: 400,
        headers: { "content-type": "application/json" },
      });
    }
  }

  try {
    await context.env.DB.prepare(
      `INSERT INTO articles
        (slug, category, player_name, team_name, title, summary_lines, source_url, source_url_normalized, source_name, published_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
      .bind(
        payload.slug,
        payload.category,
        payload.player_name ?? null,
        payload.team_name ?? null,
        payload.title,
        JSON.stringify(payload.summary_lines),
        payload.source_url,
        payload.source_url_normalized,
        payload.source_name ?? null,
        payload.published_at
      )
      .run();
  } catch (e: any) {
    // UNIQUE制約違反(source_url_normalizedの重複)は成功扱いにする。
    // main.py側の重複防止ロジック(4-22)をすり抜けた場合の二重投稿防止の最終防波堤。
    if (String(e?.message ?? e).includes("UNIQUE")) {
      return new Response(JSON.stringify({ status: "duplicate_skipped" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }
    return new Response(JSON.stringify({ error: String(e?.message ?? e) }), {
      status: 500,
      headers: { "content-type": "application/json" },
    });
  }

  return new Response(JSON.stringify({ status: "created", slug: payload.slug }), {
    status: 201,
    headers: { "content-type": "application/json" },
  });
};
