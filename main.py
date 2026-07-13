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

# OpenRouterのフォールバック先モデル（無料枠モデル）
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324:free")

# Gemini呼び出しのリトライ設定
GEMINI_MAX_RETRIES = 3
GEMINI_RETRY_WAIT_SECONDS = 20

# 各APIコールの間に空けるインターバル（レートリミット予防）
API_CALL_INTERVAL_SECONDS = 4

# 競技カテゴリごとのA8.net広告（ad-sectionに表示するリンク）
# ※ Amazon/楽天は未提携のため撤去し、A8.net一本化。
# ※ 各カテゴリはリスト形式：複数のA8案件（即時提携のものを推奨）を登録しておくと、
#    投稿のたびにランダムでローテーション表示され、自動でA/Bテストになる。
#    1件だけ登録した場合は常にその広告が使われる（従来と同じ挙動）。
# ※ URLは実際にA8.netの管理画面で発行した「素材コード（aタグ）」のhref部分に差し替えること。
AFFILIATE_ADS = {
    "SOCCER": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】海外サッカーを見るならこちら</a>',
    ],
    "BASEBALL": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】メジャー・プロ野球の生中継はこちら</a>',
    ],
    "BASKETBALL": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】NBA・Bリーグの生中継はこちら</a>',
    ],
    "WRESTLING": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-ABEMA" target="_blank" rel="nofollow noopener">【ABEMA】プロレス配信はこちら</a>',
    ],
    "COMBAT_SPORTS": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-UNEXT" target="_blank" rel="nofollow noopener">【U-NEXT】UFC・RIZIN配信はこちら</a>',
    ],
    "BOXING": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-UNEXT" target="_blank" rel="nofollow noopener">【U-NEXT】世界戦のライブ配信はこちら</a>',
    ],
    "VOLLEYBALL": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】バレーボール中継はこちら</a>',
    ],
    "AMERICAN_FOOTBALL": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】NFL生中継はこちら</a>',
    ],
    "ICE_HOCKEY": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】NHL生中継はこちら</a>',
    ],
    "RUGBY": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】ラグビー中継はこちら</a>',
    ],
    "CRICKET": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-VOD" target="_blank" rel="nofollow noopener">【配信サービス】クリケット中継はこちら</a>',
    ],
    "MOTORSPORT": [
        '<a href="https://px.a8.net/svt/ejp?a8mat=XXXXXX-DAZN" target="_blank" rel="nofollow noopener">【DAZN】F1・MotoGP生中継はこちら</a>',
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
TITLE: [元記事とは全く違う、ファンが読みたくなるキャッチーなオリジナル独自タイトル]
SUMMARY:
・【公式発表の事実】（移籍先、契約年数、移籍金など、ニュースから読み取れる客観的な事実データを1行で記述）
・【戦力的な影響・見どころ】（この移籍によってチームがどう変わるか、どのような活躍が期待されるかをあなたの言葉で1行で解説）
・【今後の注目ポイント】（次のシーズンや、今後のチーム編成に与える影響などをあなたの言葉で1行で解説）

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
                model="gemini-1.5-flash",
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
    """AIの出力テキストからカテゴリ・選手名・タイトル・要約(箇条書きリスト)を分解・抽出する"""
    lines = output_text.split("\n")
    category = "OTHER"
    player_name = ""
    title = ""
    summary_lines = []
    is_summary = False

    for line in lines:
        if line.startswith("CATEGORY:"):
            category = line.replace("CATEGORY:", "").strip()
        elif line.startswith("PLAYER_NAME:"):
            player_name = line.replace("PLAYER_NAME:", "").strip()
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

    return category, player_name, title, summary_lines


def build_blog_body(category, player_name, summary_lines, source_url):
    """元デザイン（3行要約リスト・選手グッズ個別リンク・VOD広告）に沿った記事本文HTMLを組み立てる"""
    summary_html = "\n".join(f"            <li>{line}</li>" for line in summary_lines)

    # 楽天・Amazonは現在未提携のため広告表示なし（提携完了後に再実装する）。
    # player_nameは将来の選手別広告拡張のために引数として残してあるが、現状は未使用。
    _ = player_name  # 現状未使用（将来の選手別A8案件マッチング用に保持）

    ad_candidates = AFFILIATE_ADS.get(category, AFFILIATE_ADS["OTHER"])
    vod_ad_html = random.choice(ad_candidates)

    blog_body = f"""
    <div class="article-outer">
        <div class="article-body">
            <ul class="summary-list">
{summary_html}
            </ul>
        </div>
        <div class="ad-section">
            <div class="ad-caption">ADVERTISEMENT</div>
            {vod_ad_html}
        </div>
        <p><small style="color: #999999; display: block; margin-top: 30px; font-size: 12px;">
            ※本記事は公式発表の事実データをもとに独自の解説を加えたものです。<br>
            ニュースの完全な詳細は、以下の情報元メディアにてご確認ください。<br>
            情報元URL: <a href="{source_url}" target="_blank" rel="nofollow noopener">{source_url}</a>
        </small></p>
    </div>
    """
    return blog_body


def send_to_blog(subject, body_html, category, publish=True):
    """AtomPub APIを使ってライブドアブログへ記事を投稿する

    category      : main.py内のカテゴリコード（例: "SOCCER"）。CATEGORY_LABELSで日本語ラベルに変換して送信する。
                     ライブドア側に同名カテゴリが無ければ自動で新規作成される。
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
    print(f"巡回対象RSS数: {len(all_rss_urls)}件（公式RSS {len(RSS_URLS)}件 + 競技別Google Newsキーワード {len(all_rss_urls) - len(RSS_URLS)}件）")

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
                continue  # 重複排除

            print(f"未着手の新規記事を発見しました: {entry.title}")
            raw_output = check_and_summarize_with_gemini(entry.title, entry.get("summary", ""))

            # レートリミット予防のため、AI呼び出し1回ごとに一定間隔を空ける
            time.sleep(API_CALL_INTERVAL_SECONDS)

            if not raw_output:
                print("移籍・去就情報ではないためスキップ、またはAPIエラーです。")
                save_processed_url(url)
                continue

            category, player_name, blog_title, summary_lines = parse_ai_output(raw_output)
            if not blog_title:
                blog_title = entry.title
            if not summary_lines:
                print("要約の抽出に失敗したためスキップします。")
                save_processed_url(url)
                continue

            blog_body = build_blog_body(category, player_name, summary_lines, url)

            success = send_to_blog(blog_title, blog_body, category, publish=False)
            if success:
                save_processed_url(url)
                print("1件の配信処理が正常終了したため、スクリプトを終了します。")
                sys.exit(0)


if __name__ == "__main__":
    main()
