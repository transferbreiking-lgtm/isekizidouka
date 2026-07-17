import os
import sys
import time
import random
import urllib.parse
import xml.etree.ElementTree as ET
import feedparser
import requests
from requests.auth import HTTPBasicAuth
from google import genai
from googlenewsdecoder import new_decoderv1

# -----------------------------------------------------------------------------
# 1. 設定・環境変数
# -----------------------------------------------------------------------------
# ① 検証済みの公式RSSフィード（そのまま使えるURL）
RSS_URLS = [
    "https://web.gekisaka.jp/feed",                        # ゲキサカ 全体
    "https://web.gekisaka.jp/feed?category=nationalteam",  # ゲキサカ 日本代表
    "https://web.gekisaka.jp/feed?category=domestic",      # ゲキサカ Jリーグ・国内
    "https://web.gekisaka.jp/feed?category=youth",         # ゲキサカ 高校&大学
    "https://web.gekisaka.jp/feed?category=foreign",       # ゲキサカ 海外サッカー
    "https://feeds.bbci.co.uk/sport/football/rss.xml",     # BBC Sport Football
    "https://www.mlbtraderumors.com/feed",                 # MLB Trade Rumors
]

# ② Google Newsキーワード検索RSS（世界中のプロスポーツを競技別に網羅）
#    Yahoo!ニュースとNPB.jpは方針により除外(-site:)している。
SPORT_QUERIES = {
    "SOCCER": [
        "Jリーグ 移籍 -site:yahoo.co.jp",
        "なでしこジャパン WEリーグ 移籍 -site:yahoo.co.jp",
        "日本代表 サッカー 移籍 -site:yahoo.co.jp",
        "プレミアリーグ 移籍 -site:yahoo.co.jp",
        "ラ・リーガ 移籍 -site:yahoo.co.jp",
        "セリエA サッカー 移籍 -site:yahoo.co.jp",
        "ブンデスリーガ 移籍 -site:yahoo.co.jp",
        "リーグアン 移籍 -site:yahoo.co.jp",
        "エールディビジ 移籍 -site:yahoo.co.jp",
        "プリメイラリーガ ポルトガル 移籍 -site:yahoo.co.jp",
        "ベルギーリーグ サッカー 移籍 -site:yahoo.co.jp",
        "スコティッシュプレミアシップ 移籍 -site:yahoo.co.jp",
        "トルコ スュペルリグ 移籍 -site:yahoo.co.jp",
        "MLS サッカー 移籍 -site:yahoo.co.jp",
        "ブラジル セリエA サッカー 移籍 -site:yahoo.co.jp",
        "アルゼンチン リーガプロフェシオナル 移籍 -site:yahoo.co.jp",
        "サウジプロリーグ 移籍 -site:yahoo.co.jp",
        "Kリーグ サッカー 移籍 -site:yahoo.co.jp",
        "中国スーパーリーグ サッカー 移籍 -site:yahoo.co.jp",
        "Aリーグ サッカー オーストラリア 移籍 -site:yahoo.co.jp",
        "インドスーパーリーグ 移籍 -site:yahoo.co.jp",
        "サッカー 移籍市場 -site:yahoo.co.jp",
        "サッカー 移籍金 -site:yahoo.co.jp",
    ],
    "BASEBALL": [
        "プロ野球 移籍 -site:yahoo.co.jp -site:npb.jp",
        "MLB 移籍 -site:yahoo.co.jp",
        "MLB トレード -site:yahoo.co.jp",
        "MLB FA 契約 -site:yahoo.co.jp",
        "韓国プロ野球 KBO 移籍 -site:yahoo.co.jp",
        "台湾プロ野球 CPBL 移籍 -site:yahoo.co.jp",
    ],
    "BASKETBALL": [
        "Bリーグ 移籍 -site:yahoo.co.jp",
        "NBA 移籍 -site:yahoo.co.jp",
        "NBA トレード -site:yahoo.co.jp",
        "NBA FA 契約 -site:yahoo.co.jp",
        "ユーロリーグ バスケ 移籍 -site:yahoo.co.jp",
        "中国CBA バスケ 移籍 -site:yahoo.co.jp",
    ],
    "WRESTLING": [
        "新日本プロレス 移籍 -site:yahoo.co.jp",
        "新日本プロレス 契約更改 -site:yahoo.co.jp",
        "全日本プロレス 移籍 -site:yahoo.co.jp",
        "プロレスリングノア 移籍 -site:yahoo.co.jp",
        "DDTプロレス 移籍 -site:yahoo.co.jp",
        "スターダム 女子プロレス 移籍 -site:yahoo.co.jp",
        "女子プロレス 移籍 -site:yahoo.co.jp",
        "WWE 移籍 -site:yahoo.co.jp",
        "WWE 契約 -site:yahoo.co.jp",
        "AEW 契約 -site:yahoo.co.jp",
        "Impact Wrestling 契約 -site:yahoo.co.jp",
        "ROH プロレス 契約 -site:yahoo.co.jp",
        "メキシコ CMLL ルチャリブレ 契約 -site:yahoo.co.jp",
        "AAA ルチャリブレ 契約 -site:yahoo.co.jp",
    ],
    "COMBAT_SPORTS": [
        "UFC 契約 -site:yahoo.co.jp",
        "UFC 移籍 -site:yahoo.co.jp",
        "Bellator MMA 契約 -site:yahoo.co.jp",
        "ONE Championship 契約 -site:yahoo.co.jp",
        "RIZIN 契約 -site:yahoo.co.jp",
        "PFL MMA 契約 -site:yahoo.co.jp",
        "修斗 契約 -site:yahoo.co.jp",
        "K-1 契約 -site:yahoo.co.jp",
    ],
    "BOXING": [
        "ボクシング 世界戦 契約 -site:yahoo.co.jp",
        "日本ボクシング 契約 -site:yahoo.co.jp",
        "WBA 世界タイトル 契約 -site:yahoo.co.jp",
        "WBC 世界タイトル 契約 -site:yahoo.co.jp",
        "IBF 世界タイトル 契約 -site:yahoo.co.jp",
        "WBO 世界タイトル 契約 -site:yahoo.co.jp",
        "PBC ボクシング 契約 -site:yahoo.co.jp",
    ],
    "VOLLEYBALL": [
        "SVリーグ 移籍 -site:yahoo.co.jp",
        "バレーボール 日本代表 移籍 -site:yahoo.co.jp",
    ],
    "AMERICAN_FOOTBALL": [
        "NFL 移籍 -site:yahoo.co.jp",
        "NFL トレード -site:yahoo.co.jp",
        "NFL FA 契約 -site:yahoo.co.jp",
    ],
    "ICE_HOCKEY": [
        "NHL 移籍 -site:yahoo.co.jp",
        "NHL トレード -site:yahoo.co.jp",
    ],
    "RUGBY": [
        "ラグビー 移籍 -site:yahoo.co.jp",
        "リーグワン ラグビー 移籍 -site:yahoo.co.jp",
        "スーパーラグビー 移籍 -site:yahoo.co.jp",
    ],
    "CRICKET": [
        "IPL クリケット 移籍 -site:yahoo.co.jp",
    ],
    "MOTORSPORT": [
        "F1 移籍 -site:yahoo.co.jp",
        "MotoGP 移籍 -site:yahoo.co.jp",
    ],
}

DB_FILE = "processed_urls.txt"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")  # フォールバック用（無料枠）
LIVEDOOR_BLOG_ID = os.environ.get("LIVEDOOR_BLOG_ID")
LIVEDOOR_API_KEY = os.environ.get("LIVEDOOR_API_KEY")
# チーム別カテゴリアーカイブのURL組み立てに使う独自ドメイン（末尾スラッシュ必須）
BLOG_BASE_URL = os.environ.get("BLOG_BASE_URL", "https://transferbreiking.officialblog.jp/")

# OpenRouterのフォールバック先モデル（無料枠モデル）
# ※ deepseek/deepseek-chat-v3-0324:free は2026年7月時点で無料枠が廃止され有料化された。
#    OpenRouterの無料モデルは入れ替わりが激しいので、時々 https://openrouter.ai/models?max_price=0 で
#    現行の無料ラインナップを確認し、必要ならここを更新すること。
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

# Gemini呼び出しのリトライ設定
GEMINI_MAX_RETRIES = 3
GEMINI_RETRY_WAIT_SECONDS = 20

# 各APIコールの間に空けるインターバル（レートリミット予防）
API_CALL_INTERVAL_SECONDS = 4

# Google Newsリンクのデコード処理の内部待機秒数（googlenewsdecoderライブラリの引数）
GNEWS_DECODE_INTERVAL_SECONDS = 1

# カテゴリ別サムネイル画像（ライブドアの「画像/ファイル」にアップロード済みのオリジナルバナー）
# トップページ/アーカイブページの <$ArticleFirstImage$> はこの画像を自動的に拾って一覧に表示する。
# ※ 2026年7月版バナーに差し替え済み（フルサイズURL。-s付きはサムネイル版なのでここでは使わない）。
THUMBNAIL_IMAGES = {
    "SOCCER": "https://livedoor.blogimg.jp/transfer_breiking/imgs/c/c/ccae064b.png",
    "BASEBALL": "https://livedoor.blogimg.jp/transfer_breiking/imgs/1/5/153f160a.png",
    "BASKETBALL": "https://livedoor.blogimg.jp/transfer_breiking/imgs/4/1/41690533.jpg",
    "WRESTLING": "https://livedoor.blogimg.jp/transfer_breiking/imgs/f/3/f3cac0f0.png",
    "COMBAT_SPORTS": "https://livedoor.blogimg.jp/transfer_breiking/imgs/8/a/8ad16465.png",
    "BOXING": "https://livedoor.blogimg.jp/transfer_breiking/imgs/5/9/59372024.png",
    "VOLLEYBALL": "https://livedoor.blogimg.jp/transfer_breiking/imgs/b/f/bf2b7310.jpg",
    "AMERICAN_FOOTBALL": "https://livedoor.blogimg.jp/transfer_breiking/imgs/7/7/7728614a.jpg",
    "ICE_HOCKEY": "https://livedoor.blogimg.jp/transfer_breiking/imgs/0/7/074b7ad7.jpg",
    "RUGBY": "https://livedoor.blogimg.jp/transfer_breiking/imgs/7/2/725eb216.png",
    "CRICKET": "https://livedoor.blogimg.jp/transfer_breiking/imgs/f/6/f67875e2.jpg",
    "MOTORSPORT": "https://livedoor.blogimg.jp/transfer_breiking/imgs/a/b/ab625684.jpg",
    "OTHER": "https://livedoor.blogimg.jp/transfer_breiking/imgs/0/f/0f2ab819.jpg",
}

# 競技カテゴリごとのアフィリエイト広告（ad-sectionに表示するリンク）
# ※ 複数ASPを混在させる場合も、リスト内にHTMLリンク文字列をそのまま追加すればよい
#    （投稿のたびに random.choice でランダムローテーションされ、自動でA/Bテストになる）。
# ※ A8.netにはDAZN・U-NEXTの取り扱いがないため、DAZN案件はアクセストレード、
#    U-NEXT案件はバリューコマースで別途提携し、そのリンクをここに追加している。
# ※ 下記の "XXXXXX" 部分は全てプレースホルダー。各ASPの管理画面で発行した
#    実際の素材コード（rk=... / sid=...&pid=... 等）に差し替えること。
AFFILIATE_ADS = {
    "SOCCER": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】海外サッカーを見るならこちら</a>',
        '<a href="https://px.affiliate.accesstrade.net/km_r?rk=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】海外サッカーを見るならこちら</a>',
    ],
    "BASEBALL": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】メジャー・プロ野球の生中継はこちら</a>',
        '<a href="https://px.affiliate.accesstrade.net/km_r?rk=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】メジャー・プロ野球の生中継はこちら</a>',
    ],
    "BASKETBALL": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】NBA・Bリーグの生中継はこちら</a>',
        '<a href="https://px.affiliate.accesstrade.net/km_r?rk=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】NBA・Bリーグの生中継はこちら</a>',
    ],
    "WRESTLING": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-ABEMA" target="_blank" rel="nofollow noopener">【ABEMA】プロレス配信はこちら</a>',
    ],
    "COMBAT_SPORTS": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-UNEXT" target="_blank" rel="nofollow noopener">【U-NEXT】UFC・RIZIN配信はこちら</a>',
        '<a href="https://ck.jp.ap.valuecommerce.com/servlet/referral?sid=XXXXXX&pid=XXXXXX-UNEXT" target="_blank" rel="nofollow noopener">【U-NEXT】UFC・RIZIN配信はこちら</a>',
    ],
    "BOXING": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-UNEXT" target="_blank" rel="nofollow noopener">【U-NEXT】世界戦のライブ配信はこちら</a>',
        '<a href="https://ck.jp.ap.valuecommerce.com/servlet/referral?sid=XXXXXX&pid=XXXXXX-UNEXT" target="_blank" rel="nofollow noopener">【U-NEXT】世界戦のライブ配信はこちら</a>',
    ],
    "VOLLEYBALL": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】バレーボール中継はこちら</a>',
        '<a href="https://px.affiliate.accesstrade.net/km_r?rk=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】バレーボール中継はこちら</a>',
    ],
    "AMERICAN_FOOTBALL": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】NFL生中継はこちら</a>',
        '<a href="https://px.affiliate.accesstrade.net/km_r?rk=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】NFL生中継はこちら</a>',
    ],
    "ICE_HOCKEY": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】NHL生中継はこちら</a>',
        '<a href="https://px.affiliate.accesstrade.net/km_r?rk=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】NHL生中継はこちら</a>',
    ],
    "RUGBY": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】ラグビー中継はこちら</a>',
        '<a href="https://px.affiliate.accesstrade.net/km_r?rk=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】ラグビー中継はこちら</a>',
    ],
    "CRICKET": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-VOD" target="_blank" rel="nofollow noopener">【配信サービス】クリケット中継はこちら</a>',
    ],
    "MOTORSPORT": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】F1・MotoGP生中継はこちら</a>',
        '<a href="https://px.affiliate.accesstrade.net/km_r?rk=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】F1・MotoGP生中継はこちら</a>',
    ],
    "OTHER": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-VOD" target="_blank" rel="nofollow noopener">【注目】人気のスポーツ配信サービスはこちら</a>',
    ],
}

# GeminiのCATEGORY選択肢
CATEGORY_LIST_TEXT = ", ".join(list(AFFILIATE_ADS.keys()))

# ライブドアブログの記事カテゴリとして登録する日本語ラベル
# （AtomPubは存在しないカテゴリ名を投稿すると自動で新規作成してくれる）
CATEGORY_LABELS = {
    "SOCCER": "サッカー",
    "BASEBALL": "野球",
    "BASKETBALL": "バスケットボール",
    "WRESTLING": "プロレス",
    "COMBAT_SPORTS": "格闘技",
    "BOXING": "ボクシング",
    "VOLLEYBALL": "バレーボール",
    "AMERICAN_FOOTBALL": "アメリカンフットボール",
    "ICE_HOCKEY": "アイスホッケー",
    "RUGBY": "ラグビー",
    "CRICKET": "クリケット",
    "MOTORSPORT": "モータースポーツ",
    "OTHER": "スポーツ",
}

# 出典リンクの表示名マッピング（ドメイン → サイト名）。
# 未登録ドメインは get_source_name() 内でフォールバック処理される。
SOURCE_SITE_NAMES = {
    "goal.com": "Goal.com",
    "skysports.com": "Sky Sports",
    "bbc.com": "BBC Sport",
    "bbc.co.uk": "BBC Sport",
    "espn.com": "ESPN",
    "theathletic.com": "The Athletic",
    "marca.com": "Marca",
    "as.com": "AS",
    "gazzetta.it": "Gazzetta dello Sport",
    "lequipe.fr": "L'Équipe",
    "kicker.de": "Kicker",
    "football-italia.net": "Football Italia",
    "givemesport.com": "GiveMeSport",
    "mirror.co.uk": "The Mirror",
    "dailymail.co.uk": "Daily Mail",
    "telegraph.co.uk": "The Telegraph",
    "theguardian.com": "The Guardian",
    "nytimes.com": "New York Times",
    "espncricinfo.com": "ESPNcricinfo",
    "mlb.com": "MLB.com",
    "nba.com": "NBA.com",
    "mlbtraderumors.com": "MLB Trade Rumors",
    "web.gekisaka.jp": "ゲキサカ",
    "gekisaka.jp": "ゲキサカ",
    "news.google.com": "Google News",
}


# -----------------------------------------------------------------------------
# 2. 各種処理を行う関数群
# -----------------------------------------------------------------------------
def build_google_news_rss(query):
    """キーワードをGoogle Newsの検索RSS URLに変換する"""
    encoded_query = urllib.parse.quote_plus(query)
    return f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"


def get_all_rss_urls():
    """公式RSS一覧 と 競技別Google Newsキーワード検索RSS一覧をまとめて返す"""
    google_news_urls = []
    for queries in SPORT_QUERIES.values():
        for q in queries:
            google_news_urls.append(build_google_news_rss(q))
    return RSS_URLS + google_news_urls


def get_source_name(url):
    """URLからドメインを抽出し、登録済みサイト名を返す。未登録の場合はドメイン名を整形して返す"""
    try:
        domain = urllib.parse.urlparse(url).netloc.lower()
        domain = domain[4:] if domain.startswith("www.") else domain
        if domain in SOURCE_SITE_NAMES:
            return SOURCE_SITE_NAMES[domain]
        # 未登録ドメインのフォールバック: example.com → Example
        base = domain.split(".")[0]
        return base.capitalize() if base else "情報元サイト"
    except Exception:
        return "情報元サイト"


def resolve_article_url(url):
    """Google Newsのリダイレクトリンク（news.google.com/...）を実際の掲載元URLに変換する。
    Google News以外のURL、またはデコードに失敗した場合は元のURLをそのままフォールバックとして返す。
    これにより出典表示が「Google News」ではなく実際のメディア名になり、信頼性の見え方が改善する。
    副次効果として、複数の検索クエリ経由で同じ記事が別々のGoogle Newsリンクとしてヒットしても、
    実URLに変換した後で重複判定するため、二重投稿の防止にも役立つ。"""
    try:
        domain = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return url

    if "news.google.com" not in domain:
        return url  # Google News以外のURLはそのまま返す（公式RSS等）

    try:
        result = new_decoderv1(url, interval=GNEWS_DECODE_INTERVAL_SECONDS)
        if result.get("status") and result.get("decoded_url"):
            return result["decoded_url"]
        print(f"Google Newsリンクのデコードに失敗しました（status=False）。元のURLを使用します: {url}")
    except Exception as e:
        print(f"Google Newsリンクのデコード中にエラーが発生しました。元のURLを使用します: {e}")

    return url  # デコード失敗時は元のURL（news.google.com）にフォールバック


def load_processed_urls():
    """既読URLリストファイルを読み込み、重複排除用のセットを返す"""
    if not os.path.exists(DB_FILE):
        return set()
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def save_processed_url(url):
    """新しく投稿（またはスルー）したURLを既読リストファイルへ追記する"""
    with open(DB_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")


def build_prompt(title, summary_text):
    """Gemini/OpenRouter共通の指示文（プロンプト）を組み立てる"""
    return f"""
あなたはプロのスポーツライターです。
与えられたニュースから「事実データ」のみを抽出し、元の文章の表現を一切真似せずに、読者がワクワクする完全オリジナルのコラム記事を1から執筆してください。

【対象ニュースタイトル】: {title}
【対象ニュース本文・概要】: {summary_text}

■ 処理ルール
1. まず、ニュースが「選手の移籍・引退・加入・契約更新などの去就情報」に関するものか厳格に判定してください。
2. 試合結果、戦評、日常の雑記など、去就に関係のないニュースであれば、ただ一言「SKIP」とだけ出力してください。解説は一切不要です。
3. 去就情報である場合は、元記事の文体や表現を絶対に流用（コピペ）せず、以下のフォーマットに則って完全オリジナル文章で出力してください。

■ 出力フォーマット
CATEGORY: [{CATEGORY_LIST_TEXT} のいずれかから、最も近いものを選んでください]
PLAYER_NAME: [ニュースの中心となる選手名を1名だけ、フルネームで記載してください。チーム全体の話題などで個人名が特定できない場合は「不明」と記載してください]
TEAM_NAME: [この移籍・契約等の中心となるチーム・クラブ名を1つだけ記載してください（移籍の場合は移籍先チームを優先。移籍先が未定・不明な場合は移籍元チームでも可）。正式名称または日本のメディアで一般的に使われる表記で、20文字以内で簡潔に記載してください（例: レアル・マドリード、読売ジャイアンツ、レイカーズ）。特定のチームに紐づかない話題（代表選考の一般論など）の場合は「不明」と記載してください]
TITLE: [元記事とは全く違う、ファンが読みたくなるキャッチーなオリジナル独自タイトル]
SUMMARY:
・（1行目：まず記事内容が「移籍」「残留・契約延長」「退団・契約解除」「契約更改」「スポンサー契約」「解雇」など何の話かを判断し、さらに公式発表済みか、現地報道・噂段階かを判断する。その2つの情報を反映した短いラベル（4〜10文字程度）を自分で作って行頭に付け、内容を1文で記述する）
・【戦力的な影響・見どころ】（この移籍・契約等によってチームがどう変わるか、どのような影響が期待されるかをあなたの言葉で1行で解説）
・【今後の注目ポイント】（今後のチーム編成や本人の去就に与える影響などをあなたの言葉で1行で解説）

■ SUMMARY出力時の重要な注意
各行は「【ラベル】本文」の形で出力してください（ラベル自体も実際の出力に含めます）。
ラベルの後の（）内は執筆の指示なので、（）自体は出力に含めず、指示に沿った自然な文章に置き換えてください。
1行目のラベルは固定文言を使い回さず、必ず「話の種類」×「情報の確度」の組み合わせで、その記事に合った言葉を都度作成してください。
話の種類の例：移籍、残留・契約延長、退団、契約解除、契約更改、スポンサー契約、解雇・戦力外 など（これに限らず記事内容に合わせて判断する）
情報の確度の例：公式発表がある場合は「公式発表」、現地メディア・関係者情報止まりの場合は「現地報道」「噂」など、確度が分かる言葉を含める
ラベル例：【移籍の公式発表】【残留の現地報道】【契約解除が公式発表】【スポンサー契約の公式発表】【解雇の可能性・現地報道】【契約更改の公式発表】
本文の文末表現もラベルの確度と矛盾しないようにしてください（公式発表なら「〜と発表された」、現地報道・噂なら「〜と報じられている」「〜との情報がある」のように断定を避ける）。
良い例（公式発表あり）：・【移籍の公式発表】大谷翔平選手がドジャースとの契約延長に合意したことが公式発表された。契約は3年総額1.5億ドル規模とみられる。
良い例（噂段階）：・【残留の現地報道】遠藤航がリヴァプールとの契約延長で合意間近と現地メディアが報じている。正式発表はまだない。
悪い例：・【移籍の公式発表】遠藤航がリヴァプールとの契約延長で合意間近と報じられている。（← 現地報道段階なのに公式発表ラベルは矛盾）

■ 執筆上の禁止事項
- 元記事にある「～と語った」「～という」などの語尾や、文章のつながり（構成）をそのまま真似してはいけません。
- あくまで「誰がどこへ移籍したか」という事実（著作権のないデータ）だけを抜き取り、文章自体はあなたがゼロから書き起こしてください。
"""


def call_gemini_with_retry(prompt):
    """Geminiを呼び出す。429(レートリミット)の場合は待機して最大GEMINI_MAX_RETRIES回まで再試行する"""
    if not GEMINI_API_KEY:
        print("エラー: GEMINI_API_KEY が環境変数に設定されていません。")
        return None

    client = genai.Client(api_key=GEMINI_API_KEY)

    for attempt in range(1, GEMINI_MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model="gemini-flash-latest",
                contents=prompt,
            )
            return response.text.strip()
        except Exception as e:
            error_text = str(e)
            is_rate_limit = "429" in error_text or "RESOURCE_EXHAUSTED" in error_text.upper()
            if is_rate_limit and attempt < GEMINI_MAX_RETRIES:
                wait_seconds = GEMINI_RETRY_WAIT_SECONDS * attempt
                print(f"Geminiがレートリミットに到達（{attempt}回目）。{wait_seconds}秒待って再試行します。")
                time.sleep(wait_seconds)
                continue
            print(f"Gemini API 実行エラー（{attempt}回目/最大{GEMINI_MAX_RETRIES}回）: {e}")
            return None
    return None


def call_openrouter_fallback(prompt):
    """GeminiがダメだったときのフォールバックとしてOpenRouterの無料モデルを呼び出す"""
    if not OPENROUTER_API_KEY:
        print("OPENROUTER_API_KEY が未設定のため、フォールバックをスキップします。")
        return None

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
            },
            timeout=60,
        )
        if response.status_code != 200:
            print(f"OpenRouter APIエラー: ステータスコード {response.status_code} / {response.text[:300]}")
            return None

        data = response.json()
        text = data["choices"][0]["message"]["content"].strip()
        print(f"OpenRouter（{OPENROUTER_MODEL}）で代替生成しました。")
        return text
    except Exception as e:
        print(f"OpenRouter API 実行エラー: {e}")
        return None


def check_and_summarize_with_gemini(title, summary_text):
    """去就判定＋オリジナル記事生成。Gemini→(失敗時)OpenRouterの順で試す"""
    prompt = build_prompt(title, summary_text)

    res_text = call_gemini_with_retry(prompt)

    if res_text is None:
        print("Geminiでの生成に失敗したため、OpenRouterへフォールバックします。")
        res_text = call_openrouter_fallback(prompt)

    if res_text is None:
        return None

    if "SKIP" in res_text:
        return None

    return res_text


def parse_ai_output(output_text):
    """AIの出力テキストからカテゴリ・選手名・チーム名・タイトル・要約(箇条書きリスト)を分解・抽出する"""
    lines = output_text.split("\n")
    category = "OTHER"
    player_name = ""
    team_name = ""
    title = ""
    summary_lines = []
    is_summary = False

    for line in lines:
        if line.startswith("CATEGORY:"):
            category = line.replace("CATEGORY:", "").strip()
        elif line.startswith("PLAYER_NAME:"):
            player_name = line.replace("PLAYER_NAME:", "").strip()
        elif line.startswith("TEAM_NAME:"):
            team_name = line.replace("TEAM_NAME:", "").strip()
        elif line.startswith("TITLE:"):
            title = line.replace("TITLE:", "").strip()
        elif line.startswith("SUMMARY:"):
            is_summary = True
        elif is_summary and line.strip().startswith("・"):
            # 先頭の「・」を取り除いた文章だけをリストに追加する（HTMLの<li>にそのまま入れるため）
            summary_lines.append(line.strip().lstrip("・").strip())

    if category not in AFFILIATE_ADS:
        category = "OTHER"

    if player_name in ("", "不明", "None"):
        player_name = None

    # チーム名バリデーション：空・不明・None・異常に長い（AIの出力崩れ）ものは除外する。
    # ライブドアのカテゴリ名として不正な文字（改行・スラッシュ等）が混入するのも防ぐ。
    if team_name in ("", "不明", "None") or len(team_name) > 30:
        team_name = None
    else:
        team_name = team_name.replace("\n", "").replace("/", "・").strip()

    return category, player_name, team_name, title, summary_lines


def build_team_archive_url(team_name):
    """チーム名からカテゴリアーカイブページのURLを組み立てる（category/{チーム名}形式）"""
    encoded_team = urllib.parse.quote(team_name)
    return f"{BLOG_BASE_URL.rstrip('/')}/category/{encoded_team}"


def build_blog_body(category, player_name, team_name, summary_lines, source_url):
    """元デザイン（3行要約リスト・選手グッズ個別リンク・VOD広告）に沿った記事本文HTMLを組み立てる"""
    summary_html = "\n".join(f"            <li>{line}</li>" for line in summary_lines)

    # 楽天・Amazonは現在未提携のため広告表示なし（提携完了後に再実装する）。
    # player_nameは将来の選手別広告拡張のために引数として残してあるが、現状は未使用。
    _ = player_name  # 現状未使用（将来の選手別A8案件マッチング用に保持）

    ad_candidates = AFFILIATE_ADS.get(category, AFFILIATE_ADS["OTHER"])
    vod_ad_html = random.choice(ad_candidates)

    thumbnail_url = THUMBNAIL_IMAGES.get(category, THUMBNAIL_IMAGES["OTHER"])
    source_name = get_source_name(source_url)

    # チーム名が取得できた場合のみ、そのチームのカテゴリアーカイブへのリンクブロックを挿入する。
    # AtomPubはタグ割当に対応していないため、チーム名は「サブカテゴリ」として2つ目の<category>で
    # 送信し、記事本文内には既存のカテゴリアーカイブ機能を再利用した「同チームの関連記事一覧」
    # リンクを自動生成することで、タグ的な回遊導線を実現する。
    related_html = ""
    if team_name:
        team_archive_url = build_team_archive_url(team_name)
        related_html = f"""
        <div class="related-team-section" style="margin-top:16px; padding:10px 14px; background:#1a1a1c; border-left:3px solid #e4002b;">
            <a href="{team_archive_url}" style="color:#e4002b; text-decoration:none; font-weight:bold;">📌 {team_name}の関連記事一覧はこちら »</a>
        </div>"""

    blog_body = f"""
    <div class="article-outer">
        <img src="{thumbnail_url}" alt="{category}" class="article-thumbnail" style="max-width:100%; width:100%; height:auto; display:block; border:1px solid #333;" />
        <div class="article-body">
            <ul class="summary-list">
{summary_html}
            </ul>
        </div>{related_html}
        <div class="ad-section">
            <div class="ad-caption">ADVERTISEMENT</div>
            {vod_ad_html}
        </div>
        <p><small style="color: #6e6e6e; display: block; margin-top: 30px; font-size: 11px;">
            ※本記事は各情報元の事実データをもとに独自の解説を加えたものです。<br>
            ニュースの完全な詳細は、以下の情報元メディアにてご確認ください。<br>
            情報元: <a href="{source_url}" target="_blank" rel="nofollow noopener" style="color:#8a8a8a;">{source_name}</a>
        </small></p>
    </div>
    """
    return blog_body


def send_to_blog(subject, body_html, category, team_name=None, publish=True):
    """AtomPub APIを使ってライブドアブログへ記事を投稿する

    category      : main.py内のカテゴリコード（例: "SOCCER"）。CATEGORY_LABELSで日本語ラベルに変換して送信する。
                     ライブドア側に同名カテゴリが無ければ自動で新規作成される。
    team_name     : チーム名（例: "レアル・マドリード"）。指定があれば2つ目の<category>として送信し、
                     競技カテゴリとは別にチーム別カテゴリアーカイブを自動生成させる（1記事あたり最大2カテゴリ）。
                     AtomPub APIはタグ割当に対応していないため、この「2つ目のカテゴリ」方式でタグの代替とする。
    publish=True  : 即時公開
    publish=False : 下書き保存（動作確認したいときに使用）
    """
    if not all([LIVEDOOR_BLOG_ID, LIVEDOOR_API_KEY]):
        print("エラー: 投稿に必要な環境変数(LIVEDOOR_BLOG_ID / LIVEDOOR_API_KEY)が設定されていません。")
        return False

    entry = ET.Element("entry", attrib={
        "xmlns": "http://www.w3.org/2005/Atom",
        "xmlns:app": "http://www.w3.org/2007/app",
    })
    title_elm = ET.SubElement(entry, "title")
    title_elm.text = subject

    content_elm = ET.SubElement(entry, "content", attrib={"type": "text/html"})
    content_elm.text = body_html

    category_label = CATEGORY_LABELS.get(category, CATEGORY_LABELS["OTHER"])
    ET.SubElement(entry, "category", attrib={
        "scheme": f"https://livedoor.blogcms.jp/atompub/{LIVEDOOR_BLOG_ID}/category",
        "term": category_label,
    })

    # チーム名が取得できていれば、2つ目の<category>としてチーム名も送信する。
    # ライブドア側に同名カテゴリが無ければAtomPubが自動で新規作成してくれるため、
    # 事前登録は不要。これにより「category/{チーム名}」アーカイブが自動生成される。
    if team_name:
        ET.SubElement(entry, "category", attrib={
            "scheme": f"https://livedoor.blogcms.jp/atompub/{LIVEDOOR_BLOG_ID}/category",
            "term": team_name,
        })

    app_control = ET.SubElement(entry, "app:control")
    app_draft = ET.SubElement(app_control, "app:draft")
    app_draft.text = "no" if publish else "yes"

    xml_body = '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(entry, encoding="unicode")

    endpoint = f"https://livedoor.blogcms.jp/atompub/{LIVEDOOR_BLOG_ID}/article"
    headers = {"Content-Type": "application/atom+xml;type=entry;charset=utf-8"}

    try:
        response = requests.post(
            endpoint,
            data=xml_body.encode("utf-8"),
            headers=headers,
            auth=HTTPBasicAuth(LIVEDOOR_BLOG_ID, LIVEDOOR_API_KEY),
            timeout=30,
        )
        if response.status_code == 201:
            print(f"ブログへの投稿に成功しました: {subject}")
            return True
        print(f"投稿に失敗しました。ステータスコード: {response.status_code} / レスポンス: {response.text[:300]}")
        return False
    except Exception as e:
        print(f"AtomPub API 実行エラー: {e}")
        return False


# -----------------------------------------------------------------------------
# 3. メイン制御ロジック
# -----------------------------------------------------------------------------
def main():
    processed_urls = load_processed_urls()
    print(f"現在の既読URL数: {len(processed_urls)}")

    all_rss_urls = get_all_rss_urls()
    # 巡回順を毎回シャッフルする。固定順だとサッカー関連（専用RSS+クエリ数が多い）が
    # 常に先頭に来て毎回先に投稿されてしまい、他競技のチェックまで到達できないため。
    random.shuffle(all_rss_urls)
    print(f"巡回対象RSS数: {len(all_rss_urls)}件（公式RSS {len(RSS_URLS)}件 + 競技別Google Newsキーワード {len(all_rss_urls) - len(RSS_URLS)}件）※巡回順はシャッフル済み")

    for rss_url in all_rss_urls:
        print(f"RSSフィードを巡回中: {rss_url}")
        try:
            feed = feedparser.parse(rss_url)
        except Exception as e:
            print(f"RSSのパースに失敗しました ({rss_url}): {e}")
            continue

        for entry in feed.entries:
            url = entry.link
            if url in processed_urls:
                continue  # 重複排除（Google Newsリンクそのものでの既読チェック）

            # Google Newsのリダイレクトリンクなら実際の掲載元URLに変換する
            resolved_url = resolve_article_url(url)
            if resolved_url != url and resolved_url in processed_urls:
                # 別の検索クエリ経由で既に処理済みだった同一記事なので、このリンクも既読化してスキップ
                print(f"別ルートで既に処理済みの記事と判定したためスキップします: {resolved_url}")
                save_processed_url(url)
                processed_urls.add(url)
                continue

            print(f"未着手の新規記事を発見しました: {entry.title}")
            raw_output = check_and_summarize_with_gemini(entry.title, entry.get("summary", ""))

            # レートリミット予防のため、AI呼び出し1回ごとに一定間隔を空ける
            time.sleep(API_CALL_INTERVAL_SECONDS)

            if not raw_output:
                print("移籍・去就情報ではないためスキップ、またはAPIエラーです。")
                save_processed_url(url)
                if resolved_url != url:
                    save_processed_url(resolved_url)
                continue

            category, player_name, team_name, blog_title, summary_lines = parse_ai_output(raw_output)
            if not blog_title:
                blog_title = entry.title
            if not summary_lines:
                print("要約の抽出に失敗したためスキップします。")
                save_processed_url(url)
                if resolved_url != url:
                    save_processed_url(resolved_url)
                continue

            blog_body = build_blog_body(category, player_name, team_name, summary_lines, resolved_url)

            success = send_to_blog(blog_title, blog_body, category, team_name=team_name, publish=True)
            if success:
                save_processed_url(url)
                if resolved_url != url:
                    save_processed_url(resolved_url)
                print("1件の配信処理が正常終了したため、スクリプトを終了します。")
                sys.exit(0)


if __name__ == "__main__":
    main()
