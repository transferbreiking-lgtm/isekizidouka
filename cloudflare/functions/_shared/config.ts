// main.pyのCATEGORY_LABELS/THUMBNAIL_IMAGES/AFFILIATE_ADS等と同じ内容をTypeScript側にも持たせたもの。
// D1にはカテゴリコード(例: "SOCCER")のみ保存し、表示に必要なラベル・画像・広告はここで解決する。

export const CATEGORY_LABELS: Record<string, string> = {
  SOCCER: "サッカー",
  BASEBALL: "野球",
  BASKETBALL: "バスケットボール",
  WRESTLING: "プロレス",
  COMBAT_SPORTS: "格闘技",
  BOXING: "ボクシング",
  VOLLEYBALL: "バレーボール",
  AMERICAN_FOOTBALL: "アメリカンフットボール",
  ICE_HOCKEY: "アイスホッケー",
  RUGBY: "ラグビー",
  CRICKET: "クリケット",
  MOTORSPORT: "モータースポーツ",
  OTHER: "スポーツ",
};

// 移行フェーズ1では、既存Livedoorにアップロード済みのバナー画像URLをそのまま再利用する
// （Cloudflare R2への再アップロードは、Livedoor側を閉じるタイミングで別途対応する）。
export const THUMBNAIL_IMAGES: Record<string, string> = {
  SOCCER: "https://livedoor.blogimg.jp/transfer_breiking/imgs/c/c/ccae064b.png",
  BASEBALL: "https://livedoor.blogimg.jp/transfer_breiking/imgs/1/5/153f160a.png",
  BASKETBALL: "https://livedoor.blogimg.jp/transfer_breiking/imgs/4/1/41690533.jpg",
  WRESTLING: "https://livedoor.blogimg.jp/transfer_breiking/imgs/f/3/f3cac0f0.png",
  COMBAT_SPORTS: "https://livedoor.blogimg.jp/transfer_breiking/imgs/8/a/8ad16465.png",
  BOXING: "https://livedoor.blogimg.jp/transfer_breiking/imgs/5/9/59372024.png",
  VOLLEYBALL: "https://livedoor.blogimg.jp/transfer_breiking/imgs/b/f/bf2b7310.jpg",
  AMERICAN_FOOTBALL: "https://livedoor.blogimg.jp/transfer_breiking/imgs/7/7/7728614a.jpg",
  ICE_HOCKEY: "https://livedoor.blogimg.jp/transfer_breiking/imgs/0/7/074b7ad7.jpg",
  RUGBY: "https://livedoor.blogimg.jp/transfer_breiking/imgs/7/2/725eb216.png",
  CRICKET: "https://livedoor.blogimg.jp/transfer_breiking/imgs/f/6/f67875e2.jpg",
  MOTORSPORT: "https://livedoor.blogimg.jp/transfer_breiking/imgs/a/b/ab625684.jpg",
  OTHER: "https://livedoor.blogimg.jp/transfer_breiking/imgs/0/f/0f2ab819.jpg",
};

const ABEMA_URL = "https://px.a8.net/svt/ejp?a8mat=4B878W+CTF8MY+4EKC+60WN6";

export function getAdHtml(category: string): string {
  const label = CATEGORY_LABELS[category] ?? CATEGORY_LABELS.OTHER;
  return `<a href="${ABEMA_URL}" target="_blank" rel="nofollow noopener">【ABEMA】${label}関連配信はこちら</a>`;
}

export interface Article {
  id: number;
  slug: string;
  category: string;
  player_name: string | null;
  team_name: string | null;
  title: string;
  summary_lines: string; // JSON文字列配列
  source_url: string;
  source_url_normalized: string;
  source_name: string | null;
  published_at: string;
  created_at: string;
}
