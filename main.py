import os
import sys
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
#    「移籍・契約」が実際に発生する team-based / 個人契約ベースの競技を中心に構成。
#    Yahoo!ニュースとNPB.jpは方針により除外(-site:)している。
SPORT_QUERIES = {
    "SOCCER": [
        # 国内
        "Jリーグ 移籍 -site:yahoo.co.jp",
        "なでしこジャパン WEリーグ 移籍 -site:yahoo.co.jp",
        "日本代表 サッカー 移籍 -site:yahoo.co.jp",
        # 欧州5大リーグ
        "プレミアリーグ 移籍 -site:yahoo.co.jp",
        "ラ・リーガ 移籍 -site:yahoo.co.jp",
        "セリエA サッカー 移籍 -site:yahoo.co.jp",
        "ブンデスリーガ 移籍 -site:yahoo.co.jp",
        "リーグアン 移籍 -site:yahoo.co.jp",
        # 欧州その他
        "エールディビジ 移籍 -site:yahoo.co.jp",
        "プリメイラリーガ ポルトガル 移籍 -site:yahoo.co.jp",
        "ベルギーリーグ サッカー 移籍 -site:yahoo.co.jp",
        "スコティッシュプレミアシップ 移籍 -site:yahoo.co.jp",
        "トルコ スュペルリグ 移籍 -site:yahoo.co.jp",
        # 南北米
        "MLS サッカー 移籍 -site:yahoo.co.jp",
        "ブラジル セリエA サッカー 移籍 -site:yahoo.co.jp",
        "アルゼンチン リーガプロフェシオナル 移籍 -site:yahoo.co.jp",
        # アジア・中東・オセアニア
        "サウジプロリーグ 移籍 -site:yahoo.co.jp",
        "Kリーグ サッカー 移籍 -site:yahoo.co.jp",
        "中国スーパーリーグ サッカー 移籍 -site:yahoo.co.jp",
        "Aリーグ サッカー オーストラリア 移籍 -site:yahoo.co.jp",
        "インドスーパーリーグ 移籍 -site:yahoo.co.jp",
        # 国際大会・移籍市場全般
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
        # 国内団体
        "新日本プロレス 移籍 -site:yahoo.co.jp",
        "新日本プロレス 契約更改 -site:yahoo.co.jp",
        "全日本プロレス 移籍 -site:yahoo.co.jp",
        "プロレスリングノア 移籍 -site:yahoo.co.jp",
        "DDTプロレス 移籍 -site:yahoo.co.jp",
        "スターダム 女子プロレス 移籍 -site:yahoo.co.jp",
        "女子プロレス 移籍 -site:yahoo.co.jp",
        # 海外団体
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
LIVEDOOR_BLOG_ID = os.environ.get("LIVEDOOR_BLOG_ID")
LIVEDOOR_API_KEY = os.environ.get("LIVEDOOR_API_KEY")

# 各カテゴリに対応するアフィリエイト広告（A8.net等のバナー・テキストHTMLコード）
AFFILIATE_ADS = {
    "SOCCER": '<p><a href="https://a8.net...">【サッカー】ユニフォーム・観戦チケットはこちら</a></p>',
    "BASEBALL": '<p><a href="https://a8.net...">【プロ野球】関連グッズや配信サービスはこちら</a></p>',
    "BASKETBALL": '<p><a href="https://a8.net...">【バスケ】観戦チケット・グッズはこちら</a></p>',
    "WRESTLING": '<p><a href="https://a8.net...">【プロレス】チケット・配信サービスはこちら</a></p>',
    "COMBAT_SPORTS": '<p><a href="https://a8.net...">【格闘技】配信・チケットはこちら</a></p>',
    "BOXING": '<p><a href="https://a8.net...">【ボクシング】観戦チケット・配信はこちら</a></p>',
    "VOLLEYBALL": '<p><a href="https://a8.net...">【バレーボール】観戦チケットはこちら</a></p>',
    "AMERICAN_FOOTBALL": '<p><a href="https://a8.net...">【NFL】観戦グッズ・配信はこちら</a></p>',
    "ICE_HOCKEY": '<p><a href="https://a8.net...">【アイスホッケー】観戦グッズはこちら</a></p>',
    "RUGBY": '<p><a href="https://a8.net...">【ラグビー】観戦チケットはこちら</a></p>',
    "CRICKET": '<p><a href="https://a8.net...">【クリケット】配信サービスはこちら</a></p>',
    "MOTORSPORT": '<p><a href="https://a8.net...">【モータースポーツ】観戦・グッズはこちら</a></p>',
    "OTHER": '<p><a href="https://a8.net...">【注目】人気のスポーツ関連ショップはこちら</a></p>',
}

# GeminiのCATEGORY選択肢（AFFILIATE_ADSのキーと一致させる）
CATEGORY_LIST_TEXT = ", ".join(list(AFFILIATE_ADS.keys()))


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


def check_and_summarize_with_gemini(title, summary_text):
    """Gemini 1.5 Flashで「去就判定」と「事実からのオリジナル記事生成」を同時に行う"""
    if not GEMINI_API_KEY:
        print("エラー: GEMINI_API_KEY が環境変数に設定されていません。")
        return None

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""
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
TITLE: [元記事とは全く違う、ファンが読みたくなるキャッチーなオリジナル独自タイトル]
SUMMARY:
・【公式発表の事実】（移籍先、契約年数、移籍金など、ニュースから読み取れる客観的な事実データを1行で記述）
・【戦力的な影響・見どころ】（この移籍によってチームがどう変わるか、どのような活躍が期待されるかをあなたの言葉で1行で解説）
・【今後の注目ポイント】（次のシーズンや、今後のチーム編成に与える影響などをあなたの言葉で1行で解説）

■ 執筆上の禁止事項
- 元記事にある「～と語った」「～という」などの語尾や、文章のつながり（構成）をそのまま真似してはいけません。
- あくまで「誰がどこへ移籍したか」という事実（著作権のないデータ）だけを抜き取り、文章自体はあなたがゼロから書き起こしてください。
"""

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
        )
        res_text = response.text.strip()

        if "SKIP" in res_text:
            return None

        return res_text
    except Exception as e:
        print(f"Gemini API 実行エラー: {e}")
        return None


def parse_gemini_output(output_text):
    """Geminiの出力テキストからカテゴリ・タイトル・要約を分解・抽出する"""
    lines = output_text.split("\n")
    category = "OTHER"
    title = ""
    summary_lines = []
    is_summary = False

    for line in lines:
        if line.startswith("CATEGORY:"):
            category = line.replace("CATEGORY:", "").strip()
        elif line.startswith("TITLE:"):
            title = line.replace("TITLE:", "").strip()
        elif line.startswith("SUMMARY:"):
            is_summary = True
        elif is_summary and line.strip().startswith("・"):
            summary_lines.append(line.strip())

    if category not in AFFILIATE_ADS:
        category = "OTHER"

    summary_html = "<br>".join(summary_lines)
    return category, title, summary_html


def send_to_blog(subject, body_html, publish=True):
    """AtomPub APIを使ってライブドアブログへ記事を投稿する

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

            if not raw_output:
                print("移籍・去就情報ではないためスキップ、またはAPIエラーです。")
                save_processed_url(url)
                continue

            category, blog_title, blog_summary = parse_gemini_output(raw_output)
            if not blog_title:
                blog_title = entry.title

            ad_html = AFFILIATE_ADS.get(category, AFFILIATE_ADS["OTHER"])

            # ▼▼▼ スタイル(インラインCSS)はこのブロック内にあります ▼▼▼
            blog_body = f"""
            <div>
                <h3>【独自解説コラム】</h3>
                <p>{blog_summary}</p>
                <hr>
                {ad_html}
                <br>
                <p><small style="color: #666;">※本記事は公式発表の事実データをもとに独自の解説を加えたものです。<br>ニュースの完全な詳細は、以下の情報元メディアにてご確認ください。<br>情報元URL: <a href="{url}" target="_blank">{url}</a></small></p>
            </div>
            """
            # ▲▲▲ スタイル(インラインCSS)ここまで ▲▲▲

            success = send_to_blog(blog_title, blog_body, publish=True)
            if success:
                save_processed_url(url)
                print("1件の配信処理が正常終了したため、スクリプトを終了します。")
                sys.exit(0)


if __name__ == "__main__":
    main()
