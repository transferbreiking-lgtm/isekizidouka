import os
import re
import sys
import time
import uuid
import random
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import feedparser
import requests
from requests.auth import HTTPBasicAuth
from google import genai
from googlenewsdecoder import new_decoderv1

# -----------------------------------------------------------------------------
# 1. 設定・環境変数
# -----------------------------------------------------------------------------
# ① 検証済みの公式RSSフィード（そのまま使えるURL）。カテゴリ別に辞書化しておくことで、
#    main()側でカテゴリ単位に公平抽選できるようにする（サッカーだけフィード数が圧倒的に
#    多く、フラットな1本のリストでシャッフルすると統計的にサッカーへ投稿が偏るため）。
RSS_URLS_BY_CATEGORY = {
    "SOCCER": [
        "https://web.gekisaka.jp/feed",                        # ゲキサカ 全体
        "https://web.gekisaka.jp/feed?category=nationalteam",  # ゲキサカ 日本代表
        "https://web.gekisaka.jp/feed?category=domestic",      # ゲキサカ Jリーグ・国内
        "https://web.gekisaka.jp/feed?category=youth",         # ゲキサカ 高校&大学
        "https://web.gekisaka.jp/feed?category=foreign",       # ゲキサカ 海外サッカー
        "https://feeds.bbci.co.uk/sport/football/rss.xml",     # BBC Sport Football
        "https://www.espn.com/espn/rss/soccer/news",           # ESPN Soccer（海外ソース強化・2026/7/27実在確認済み）
    ],
    "BASEBALL": [
        "https://www.mlbtraderumors.com/feed",                 # MLB Trade Rumors
    ],
    "BASKETBALL": [
        "https://www.espn.com/espn/rss/nba/news",              # ESPN NBA（2026/7/27実在確認済み）
    ],
    "AMERICAN_FOOTBALL": [
        "https://www.espn.com/espn/rss/nfl/news",              # ESPN NFL（同上）
    ],
    "ICE_HOCKEY": [
        "https://www.espn.com/espn/rss/nhl/news",              # ESPN NHL（同上）
    ],
}

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

# ③ 英語版Google Newsキーワード検索（海外メディア発の一次情報を拾うための構成）。
#    hl=ja&gl=JPのクエリは「海外リーグの話題」でも「日本語メディアが翻訳・要約した記事」しか
#    拾えないため、情報元ドメインが国内メディアに偏る問題があった（2026/7/27診断）。
#    hl=en&gl=USで検索することで、BBC・ESPN・Sky Sports・Marca等の海外メディア本体の記事を
#    直接ソースにできるようにする。国内4割・海外6割の比率を目指す構成。
SPORT_QUERIES_EN = {
    "SOCCER": [
        "Premier League transfer",
        "La Liga transfer news",
        "Serie A transfer news",
        "Bundesliga transfer",
        "Ligue 1 transfer",
        "MLS transfer news",
        "football transfer deal",
        "club confirms signing football",
        "loan deal football transfer",
        "free transfer football",
    ],
    "BASEBALL": [
        "MLB trade rumors",
        "MLB free agent signing",
        "MLB trade deadline deal",
    ],
    "BASKETBALL": [
        "NBA trade rumors",
        "NBA free agency signing",
        "NBA trade deadline deal",
    ],
    "WRESTLING": [
        "WWE signs wrestler",
        "AEW signs wrestler",
        "wrestler released contract",
    ],
    "COMBAT_SPORTS": [
        "UFC signs fighter",
        "UFC fighter contract",
    ],
    "BOXING": [
        "boxer signs promotional deal",
        "boxing world title fight signed",
    ],
    "VOLLEYBALL": [
        "volleyball transfer signing",
    ],
    "AMERICAN_FOOTBALL": [
        "NFL trade rumors",
        "NFL free agency signing",
    ],
    "ICE_HOCKEY": [
        "NHL trade rumors",
        "NHL free agency signing",
    ],
    "RUGBY": [
        "rugby union transfer signing",
        "Premiership Rugby signing",
    ],
    "CRICKET": [
        "IPL auction signing",
        "cricket transfer signing",
    ],
    "MOTORSPORT": [
        "F1 driver signs contract",
        "MotoGP rider signs contract",
    ],
}

DB_FILE = "processed_urls.txt"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")  # フォールバック用（無料枠）
LIVEDOOR_BLOG_ID = os.environ.get("LIVEDOOR_BLOG_ID")
LIVEDOOR_API_KEY = os.environ.get("LIVEDOOR_API_KEY")
# チーム別カテゴリアーカイブのURL組み立てに使う独自ドメイン（末尾スラッシュ必須）
BLOG_BASE_URL = os.environ.get("BLOG_BASE_URL", "https://transferbreaking.officialblog.jp/")

# Cloudflare（新本番）への投稿先。D1書き込み用APIエンドポイントと、その認証シークレット。
# 2026/8/4のCloudflare移行により、D1側を本番の投稿先とし、Livedoorはバックグラウンド
# （従属的なミラー先）として維持する運用に切り替えた。
D1_INGEST_URL = os.environ.get("D1_INGEST_URL", "https://transferbreaking.pages.dev/api/articles")
D1_INGEST_SECRET = os.environ.get("D1_INGEST_SECRET")

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

# Google Newsリンクのデコード失敗時の最大リトライ回数。
# デコードが1回失敗しただけで元のGoogle News URLにフォールバックすると、同じ記事が
# 別の検索クエリ経由で正常デコードされた過去の記事URLと一致せず、重複投稿の原因になる
# （クリケットのように検索クエリ数が少ないカテゴリで顕在化した：2026/8/1）。
GNEWS_DECODE_MAX_RETRIES = 2

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
# ※ 2026年7月22日時点の運用方針：
#    DAZN単独／DMM×DAZNホーダイ／U-NEXTは、アクセストレード（審査落選）・A8.net（取り扱い無し）・
#    もしもアフィリエイト（取り扱い無し）・バリューコマース（取り扱い見当たらず）・afb（未登録）・
#    Felmat（クローズドASPのため対象外）と、あらゆるルートで提携が進まなかったため、いったん撤退。
#    かわりに、A8.netで既に提携済み・審査不要で確実に動く「ABEMA」の実リンク1本に、
#    全カテゴリを統一した。カテゴリごとに文言だけ変えてある。
#    今後、他ASPでDAZN/U-NEXT等の審査が通った場合は、該当カテゴリのリストにリンクを追加すれば
#    自動でランダムローテーション（A/Bテスト）に組み込まれる（このリスト構造自体は維持）。
ABEMA_AFFILIATE_URL = "https://px.a8.net/svt/ejp?a8mat=4B878W+CTF8MY+4EKC+60WN6"

AFFILIATE_ADS = {
    "SOCCER": [
        f'<a href="{ABEMA_AFFILIATE_URL}" target="_blank" rel="nofollow noopener">【ABEMA】海外サッカー・国内サッカー配信はこちら</a>',
    ],
    "BASEBALL": [
        f'<a href="{ABEMA_AFFILIATE_URL}" target="_blank" rel="nofollow noopener">【ABEMA】プロ野球・メジャーリーグ関連配信はこちら</a>',
    ],
    "BASKETBALL": [
        f'<a href="{ABEMA_AFFILIATE_URL}" target="_blank" rel="nofollow noopener">【ABEMA】NBA・Bリーグ関連配信はこちら</a>',
    ],
    "WRESTLING": [
        f'<a href="{ABEMA_AFFILIATE_URL}" target="_blank" rel="nofollow noopener">【ABEMA】プロレス配信はこちら</a>',
    ],
    "COMBAT_SPORTS": [
        f'<a href="{ABEMA_AFFILIATE_URL}" target="_blank" rel="nofollow noopener">【ABEMA】格闘技・MMA配信はこちら</a>',
    ],
    "BOXING": [
        f'<a href="{ABEMA_AFFILIATE_URL}" target="_blank" rel="nofollow noopener">【ABEMA】ボクシング世界戦配信はこちら</a>',
    ],
    "VOLLEYBALL": [
        f'<a href="{ABEMA_AFFILIATE_URL}" target="_blank" rel="nofollow noopener">【ABEMA】バレーボール関連配信はこちら</a>',
    ],
    "AMERICAN_FOOTBALL": [
        f'<a href="{ABEMA_AFFILIATE_URL}" target="_blank" rel="nofollow noopener">【ABEMA】アメリカンフットボール関連配信はこちら</a>',
    ],
    "ICE_HOCKEY": [
        f'<a href="{ABEMA_AFFILIATE_URL}" target="_blank" rel="nofollow noopener">【ABEMA】アイスホッケー関連配信はこちら</a>',
    ],
    "RUGBY": [
        f'<a href="{ABEMA_AFFILIATE_URL}" target="_blank" rel="nofollow noopener">【ABEMA】ラグビー関連配信はこちら</a>',
    ],
    "CRICKET": [
        f'<a href="{ABEMA_AFFILIATE_URL}" target="_blank" rel="nofollow noopener">【ABEMA】クリケット関連配信はこちら</a>',
    ],
    "MOTORSPORT": [
        f'<a href="{ABEMA_AFFILIATE_URL}" target="_blank" rel="nofollow noopener">【ABEMA】F1・MotoGP関連配信はこちら</a>',
    ],
    "OTHER": [
        f'<a href="{ABEMA_AFFILIATE_URL}" target="_blank" rel="nofollow noopener">【ABEMA】注目のスポーツ配信サービスはこちら</a>',
    ],
}

# 物販系のA8.net案件（総合スポーツ用品通販）。2026/7/27に提携確認済み。
# 動画配信(ABEMA)とは別枠として記事下部にもう1本表示し、視聴目的とは違う「グッズを買いたい」
# 読者の受け皿にする。全カテゴリ共通の総合通販サイトのため、AFFILIATE_ADSとは別のリストで持ち、
# build_goods_ad_html()内でランダム抽選＋team_nameを使った訴求文を組み立てる。
# 各案件のimgタグ（1x1透過ピクセル）はA8.net側のインプレッション計測用のため、削除しないこと。
GOODS_AFFILIATE_ADS = [
    {
        "name": "スーパースポーツゼビオ",
        "html": (
            '<a href="https://px.a8.net/svt/ejp?a8mat=4B8ACQ+FT6P4Q+4ABU+5YJRM" target="_blank" rel="nofollow noopener">{link_text}</a>'
            '<img border="0" width="1" height="1" src="https://www15.a8.net/0.gif?a8mat=4B8ACQ+FT6P4Q+4ABU+5YJRM" alt="">'
        ),
    },
    {
        "name": "ムラサキスポーツ",
        "html": (
            '<a href="https://px.a8.net/svt/ejp?a8mat=4B8ACQ+FUDKCA+5MZI+5YRHE" target="_blank" rel="nofollow noopener">{link_text}</a>'
            '<img border="0" width="1" height="1" src="https://www12.a8.net/0.gif?a8mat=4B8ACQ+FUDKCA+5MZI+5YRHE" alt="">'
        ),
    },
    {
        "name": "スポーツデポ",
        "html": (
            '<a href="https://px.a8.net/svt/ejp?a8mat=4B8ACQ+FTS4QI+3OSK+5YJRM" target="_blank" rel="nofollow noopener">{link_text}</a>'
            '<img border="0" width="1" height="1" src="https://www18.a8.net/0.gif?a8mat=4B8ACQ+FTS4QI+3OSK+5YJRM" alt="">'
        ),
    },
]

# team_nameが完全一致した場合に優先表示する「その対象そのものの商品」へのA8.net商品リンク
# （楽天商品リンク検索・Amazon商品リンク検索から個別に手動生成したもの）。
# GOODS_AFFILIATE_ADS（総合スポーツ用品店のトップページリンク）より、記事内容と直結した
# 具体的な商品の方がCVRが高いため、該当があればこちらを優先する（build_goods_ad_html参照）。
# 商品はモデルチェンジ・完売等で陳腐化するため、定期的な手動更新が前提の構成。
TEAM_GOODS_ADS = {
    "日本代表": [
        (
            '<a href="https://rpx.a8.net/svt/ejp?a8mat=1U7G8F+1Y9G6Y+2HOM+BWGDT&rakuten=y&a8ejpredirect=https%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2Fg00r3jp4.2bo11c31.g00r3jp4.2bo12562%2Fa04081397281_1U7G8F_1Y9G6Y_2HOM_BWGDT%3Fpc%3Dhttps%253A%252F%252Fitem.rakuten.co.jp%252Fhimaraya%252F0000001299356%252F%26m%3Dhttp%253A%252F%252Fm.rakuten.co.jp%252Fhimaraya%252Fi%252F10629520%252F%26rafcid%3Dwsc_i_is_a9f492a7-8ef9-40e2-ab89-4bc43a1ee283" target="_blank" rel="nofollow noopener">アディダス(adidas) サッカー日本代表 2026 ホーム レプリカユニフォームはこちら【楽天市場】</a>'
            '<img border="0" width="1" height="1" src="https://www12.a8.net/0.gif?a8mat=1U7G8F+1Y9G6Y+2HOM+BWGDT" alt="">'
        ),
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
    "nfl.com": "NFL.com",
    "nhl.com": "NHL.com",
    "cbssports.com": "CBS Sports",
    "foxsports.com": "Fox Sports",
    "si.com": "Sports Illustrated",
    "sportingnews.com": "Sporting News",
    "talksport.com": "talkSPORT",
    "standard.co.uk": "Evening Standard",
    "football365.com": "Football365",
    "90min.com": "90min",
    "web.gekisaka.jp": "ゲキサカ",
    "gekisaka.jp": "ゲキサカ",
    "news.google.com": "Google News",
    # 日本の主要スポーツ紙・通信社（未登録ドメインだと英語のフォールバック表記になってしまうため追加）
    "daily.co.jp": "デイリースポーツ",
    "nikkansports.com": "日刊スポーツ",
    "sponichi.co.jp": "スポニチアネックス",
    "sanspo.com": "サンスポ",
    "hochi.news": "スポーツ報知",
    "jiji.com": "時事通信",
    "asahi.com": "朝日新聞",
    "nikkei.com": "日本経済新聞",
    "mainichi.jp": "毎日新聞",
    "chunichi.co.jp": "中日スポーツ",
    "tokyo-sports.co.jp": "東京スポーツ",
    "full-count.jp": "Full-Count",
    "theanswer.jp": "THE ANSWER",
    "soccerdigestweb.com": "サッカーダイジェストWeb",
    "footballchannel.jp": "フットボールチャンネル",
    "number.bunshun.jp": "Number Web",
}


# -----------------------------------------------------------------------------
# 2. 各種処理を行う関数群
# -----------------------------------------------------------------------------
def build_google_news_rss(query, hl="ja", gl="JP"):
    """キーワードをGoogle Newsの検索RSS URLに変換する（hl/glで検索対象の言語圏を切り替え可能）"""
    encoded_query = urllib.parse.quote_plus(query)
    ceid = f"{gl}:{hl}"
    return f"https://news.google.com/rss/search?q={encoded_query}&hl={hl}&gl={gl}&ceid={ceid}"


def get_rss_urls_by_category():
    """カテゴリごとに「公式RSS + 国内語Google News検索 + 英語Google News検索」をまとめた辞書を返す。
    main()側でカテゴリを先に抽選してからフィードを巡回するために使う（フラットな1本のリストで
    シャッフルすると、フィード数が多いカテゴリ＝サッカーに投稿が統計的に偏ってしまうため）。"""
    categories = set(RSS_URLS_BY_CATEGORY) | set(SPORT_QUERIES) | set(SPORT_QUERIES_EN)
    result = {}
    for cat in categories:
        urls = list(RSS_URLS_BY_CATEGORY.get(cat, []))
        urls += [build_google_news_rss(q, hl="ja", gl="JP") for q in SPORT_QUERIES.get(cat, [])]
        urls += [build_google_news_rss(q, hl="en", gl="US") for q in SPORT_QUERIES_EN.get(cat, [])]
        result[cat] = urls
    return result


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

    for attempt in range(1, GNEWS_DECODE_MAX_RETRIES + 1):
        try:
            result = new_decoderv1(url, interval=GNEWS_DECODE_INTERVAL_SECONDS)
            if result.get("status") and result.get("decoded_url"):
                return result["decoded_url"]
            print(f"Google Newsリンクのデコードに失敗しました（{attempt}回目/最大{GNEWS_DECODE_MAX_RETRIES}回・status=False）。")
        except Exception as e:
            print(f"Google Newsリンクのデコード中にエラーが発生しました（{attempt}回目/最大{GNEWS_DECODE_MAX_RETRIES}回）: {e}")
        if attempt < GNEWS_DECODE_MAX_RETRIES:
            time.sleep(GNEWS_DECODE_INTERVAL_SECONDS)

    print(f"Google Newsリンクのデコードに最終的に失敗したため、元のURLを使用します: {url}")
    return url  # デコード失敗時は元のURL（news.google.com）にフォールバック


def normalize_resolved_url(url):
    """記事の実URLを重複判定用に正規化する（ドメインの大文字小文字・www有無・末尾スラッシュ・
    クエリ文字列/フラグメントの差異を吸収する）。同じ記事が別の検索クエリ経由で拾われた際、
    トラッキングパラメータの有無だけで別記事と誤判定されるのを防ぐために使う。"""
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parsed.path.rstrip("/")
        return f"{netloc}{path}"
    except Exception:
        return url


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
以下の【対象ニュース】は「事実の材料」としてのみ使い、翻訳や言い換えではなく、あなた自身の構成・言葉で完全オリジナルのコラム記事を1から執筆してください（対象ニュースが日本語・外国語のどちらであっても同じ方針で扱ってください）。

【対象ニュースタイトル】: {title}
【対象ニュース本文・概要】: {summary_text}

■ 処理ルール
1. まず、ニュースが「選手の移籍・引退・加入・契約更新などの去就情報」に関するものか厳格に判定してください。
2. 試合結果、戦評、日常の雑記など、去就に関係のないニュースであれば、ただ一言「SKIP」とだけ出力してください。解説は一切不要です。
3. 去就情報である場合は、以下の3ステップの順番を厳守して執筆してください。

■ 執筆ステップ（この順序を必ず守ること）
【Step1: 事実の精査】対象ニュースから「誰が／どこへ／いつ／契約条件（年数・金額等、記載があれば）」を正確に抜き出し、それが「公式発表済み」なのか「現地報道・観測段階」なのかを判定する。事実でない記者の感想・推測・煽り表現は事実と混同しない。
【Step2: 独自解釈の構築】Step1の事実をもとに、TransferBreaking独自の切り口を1つ決める（例：移籍先の戦術・布陣とのフィット、過去の類似移籍との比較、そのクラブの補強方針・ポジション競争への影響、契約構造の解説、日本サッカーとの接点など）。この切り口を記事とタイトルの軸にする。単なる事実の羅列や、対象ニュースの論調をなぞるだけの記事にしないこと。
【Step3: 執筆】Step2で決めた切り口を軸に、あなた自身の構成・語順・言葉で記事を書く。対象ニュースの文章表現・見出し・段落構成・語尾は一切模倣・翻訳しないこと。

■ 出力フォーマット
CATEGORY: [{CATEGORY_LIST_TEXT} のいずれかから、最も近いものを選んでください]
PLAYER_NAME: [ニュースの中心となる選手名を1名だけ、フルネームで記載してください。チーム全体の話題などで個人名が特定できない場合は「不明」と記載してください]
TEAM_NAME: [この移籍・契約等の中心となるチーム・クラブ名を1つだけ記載してください（移籍の場合は移籍先チームを優先。移籍先が未定・不明な場合は移籍元チームでも可）。正式名称または日本のメディアで一般的に使われる表記で、20文字以内で簡潔に記載してください（例: レアル・マドリード、読売ジャイアンツ、レイカーズ）。特定のチームに紐づかない話題（代表選考の一般論など）の場合は「不明」と記載してください]
TITLE: [以下の2つの条件を両方満たすタイトルを作成してください。
  条件1（SEO）：冒頭18〜20文字以内に「誰が」「何が起きたか（移籍/契約延長/退団など）」が伝わる言葉を置くこと。検索結果やSNSでは後半が表示されずに切れることがあるため、前半だけ読んでも内容が分かるようにする。タイトル全体は30〜38文字程度に収め、長くしすぎないこと。
  条件2（感情移入）：後半にStep2で決めた独自の切り口を反映しつつ、読者（ファン）の感情（期待・興奮・不安・誇り・悔しさなど）を動かす一言を加えること。事実の言い換えではなく、読者が「気になる」「応援したくなる」と感じる表現にする。
  対象ニュースの見出しの事実をそのまま言い換えただけのタイトルにはしないこと]
SUMMARY:
・（1行目：まず記事内容が「移籍」「残留・契約延長」「退団・契約解除」「契約更改」「スポンサー契約」「解雇」など何の話かを判断し、さらに公式発表済みか、現地報道・噂段階かを判断する。その2つの情報を反映した短いラベル（4〜10文字程度）を自分で作って行頭に付け、内容を1文で記述する）
・【背景・経緯】（Step2で決めた独自の切り口を軸に、この選手・チームの直近の状況や、過去の類似の移籍・契約事例との比較などを2文程度で解説する。単なる事実の繰り返しではなく、読者が「なるほど」と思える背景情報を補うこと）
・【戦力的な影響・見どころ】（この移籍・契約等によってチームがどう変わるか、どのような影響が期待されるかをあなたの言葉で1行で解説）
・【ファンの期待値・注目度】（この話題について、ファン・サポーターがどんな感情を抱きそうか、なぜ応援したくなるのか・注目すべきなのかを、あなたの言葉で1行で解説。ただし「なぜそう言えるのか」の根拠として、対象ニュースに含まれる具体的な数字・実績・経歴・過去の対戦成績・年齢・在籍年数などのうち最低1つを必ず本文中に明記すること。数字や具体的事実が対象ニュース中に見当たらない場合は、無理に感情を盛らず、その状況の「事実としての意味」を簡潔に述べるに留める）
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

■ 表現の多様性ルール（AI臭さ・量産感を消すために厳守）
- 1つの文の中で同じ形容詞・副詞・名詞を2回以上使ってはいけません（悪い例：「圧倒的な輝きを放った圧倒的な攻撃性能」）。書き終えたら必ず読み返し、重複があれば片方を別の言葉に置き換えるか削ってください。
- 以下の単語・言い回しは、TransferBreakingの過去記事で使われすぎているため、このタスクでは原則として使用禁止です：「覚悟」「熱量」「悲願」「執念」「ロマン」「胸を打つ」「熱い視線」「大きな注目」「大きな賞賛」「新時代」「開く」（比喩表現として）「浮上する」「最右翼」。同じ意味を表す場合は、必ずその記事固有の事実（具体的な数字・経歴・状況）に基づいた別の言葉で表現し直してください。
- 4行のSUMMARYそれぞれで、抽象的な感情語だけで文を終わらせず、可能な限り「何が原因でその感情・評価が生まれるのか」という事実的な裏付けを一言添えてください。
- タイトルも同様に、「新時代」「衝撃」「電撃」「悲願」など使い古された煽り語のワンパターン化を避け、その記事固有の事実（具体的な数字・対戦相手・経歴上の意味）を反映した言葉を優先してください。

■ 執筆上の禁止事項
- 対象ニュースが外国語の場合でも、それを翻訳して要約を作ることは禁止します。翻訳ではなく、事実だけを抜き出して日本語でゼロから書き起こしてください。
- 対象ニュースにある「～と語った」「～という」などの語尾や、見出しの発想、文章のつながり（構成）をそのまま真似してはいけません。
- あくまで「誰がどこへ移籍したか」「契約条件」などの事実（著作権のないデータ）だけを抜き取り、文章自体・タイトル・構成はあなたがゼロから書き起こしてください。
- 対象ニュース中の記者コメントや分析部分を直接引用する場合は、1箇所・15語相当以内に留め、「〜と報じている」等の形で意見であることが分かるようにしてください（事実と意見を混同しないこと）。
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


# build_prompt内の「表現の多様性ルール」で使用禁止にした紋切り型ワード一覧。
# ここでの検知は生成をブロック・再試行させるものではなく（無料枠のAPI呼び出し追加を避けるため）、
# GitHub Actionsのログに「まだ紋切り型が出ていないか」を残し、次回以降のプロンプト調整の
# 判断材料にするためだけの軽量チェック。
CLICHE_WORDS = ["覚悟", "熱量", "悲願", "執念", "ロマン", "胸を打つ", "熱い視線", "大きな注目", "大きな賞賛", "新時代", "最右翼"]


def check_cliche_and_repetition(text):
    """紋切り型ワードの使用と、同一文内での単語重複（AI臭さの典型パターン）を検知してログに出す。
    ブロッキングは行わない（ログ確認のみ）。"""
    if not text:
        return

    hit_words = [w for w in CLICHE_WORDS if w in text]
    if hit_words:
        print(f"[表現チェック] 使用禁止ワードが出力に含まれています（プロンプト遵守漏れの可能性）: {hit_words}")

    # 「。」「！」「？」で文を区切り、各文の中で4文字以上の語が連続していないか簡易チェック
    for sentence in re.split(r"[。！？]", text):
        words = re.findall(r"[ぁ-んァ-ヶ一-龠a-zA-Z]{4,}", sentence)
        seen = set()
        for w in words:
            if w in seen:
                print(f"[表現チェック] 同一文内での単語重複を検知しました: 「{w}」 / 文: {sentence.strip()[:60]}")
                break
            seen.add(w)


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

    check_cliche_and_repetition(res_text)

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


def build_goods_ad_html(category, player_name, team_name):
    """物販系のA8.net広告を1件選んで埋め込む。
    team_nameがTEAM_GOODS_ADSに完全一致する場合は、その対象そのものの具体的な商品リンク
    （例：日本代表記事→日本代表ユニフォーム）を優先表示する。記事内容と直結した商品の方が
    総合スポーツ用品店のトップページリンクよりCVRが高いため。該当が無ければGOODS_AFFILIATE_ADS
    （総合スポーツ用品店）にフォールバックし、team_name/player_nameを使った訴求文を添える。"""
    if team_name and team_name in TEAM_GOODS_ADS:
        return random.choice(TEAM_GOODS_ADS[team_name])

    ad = random.choice(GOODS_AFFILIATE_ADS)
    if team_name:
        subject = team_name
    elif player_name:
        subject = player_name
    else:
        subject = CATEGORY_LABELS.get(category, CATEGORY_LABELS["OTHER"])
    link_text = f"{subject}関連のグッズを探すなら【{ad['name']}】"
    return ad["html"].format(link_text=link_text)


def compact_html_for_description(html):
    """本文HTMLの改行・インデントを1行に圧縮する。
    Livedoorの<$ArticleDescription$>（meta description自動生成タグ）はHTMLタグを除去した
    プレーンテキストをそのまま使う仕様のため、単純に全行を空白区切りで結合すると、
    実テキストを持たないタグだけの行（<div>や<img>等）の区切りスペースがタグ除去後もそのまま
    残ってしまい、本文冒頭に構造タグの数だけ空白が並ぶ問題があった（2026/7/26に一度対策したが
    完全には解消していないことが2026/8/3の実機確認で判明）。
    実テキストを含む行の前にだけ区切りスペースを入れることで、タグ除去後に残る余分な空白を
    最小限にする。"""
    lines = [line.strip() for line in html.split("\n") if line.strip()]
    result = ""
    seen_text = False  # 最初の実テキストの手前には区切りスペース自体を入れない（冒頭の空白を完全に無くすため）
    for line in lines:
        has_text = bool(re.sub(r"<[^>]+>", "", line).strip())
        if has_text and seen_text and result and not result.endswith(" "):
            result += " "
        result += line
        if has_text:
            seen_text = True
    return re.sub(r" {2,}", " ", result).strip()


def build_blog_body(category, player_name, team_name, summary_lines, source_url):
    """元デザイン（3行要約リスト・選手グッズ個別リンク・VOD広告）に沿った記事本文HTMLを組み立てる"""
    summary_html = "\n".join(f"            <li>{line}</li>" for line in summary_lines)

    # 楽天・Amazonは現在未提携のため広告表示なし（提携完了後に再実装する）。
    ad_candidates = AFFILIATE_ADS.get(category, AFFILIATE_ADS["OTHER"])
    vod_ad_html = random.choice(ad_candidates)
    goods_ad_html = build_goods_ad_html(category, player_name, team_name)

    thumbnail_url = THUMBNAIL_IMAGES.get(category, THUMBNAIL_IMAGES["OTHER"])
    source_name = get_source_name(source_url)

    # 記事下部には「同カテゴリ（親タグ）の記事一覧」への導線バナーを常に表示する。
    # チーム別の導線は、記事上部の赤バッジ（<$ArticleCategory1$>の右隣に並ぶ<$ArticleCategory2$>）が
    # 既に担っているため、記事下部は元々の設計どおり親カテゴリへのリンクに統一する。
    category_label = CATEGORY_LABELS.get(category, CATEGORY_LABELS["OTHER"])
    category_archive_url = build_team_archive_url(category_label)  # 「チーム名」に限らず任意のカテゴリ名でアーカイブURLを組み立てられる汎用関数として利用
    related_html = f"""
        <div class="related-team-section" style="margin-top:16px; padding:10px 14px; background:#1a1a1c; border-left:3px solid #e4002b;">
            <a href="{category_archive_url}" style="color:#e4002b; text-decoration:none; font-weight:bold;">📌 {category_label}の記事一覧はこちら »</a>
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
        <div class="ad-section">
            <div class="ad-caption">SPORTS GOODS</div>
            {goods_ad_html}
        </div>
        <p><small style="color: #6e6e6e; display: block; margin-top: 30px; font-size: 11px;">
            ※本記事は各情報元の事実データをもとに独自の解説を加えたものです。<br>
            ニュースの完全な詳細は、以下の情報元メディアにてご確認ください。<br>
            情報元: <a href="{source_url}" target="_blank" rel="nofollow noopener" style="color:#8a8a8a;">{source_name}</a>
        </small></p>
    </div>
    """

    return compact_html_for_description(blog_body)


JST = timezone(timedelta(hours=9))


def generate_article_slug(category):
    """D1のarticles.slugに使うユニークなスラッグを組み立てる（日本語タイトルはURLに向かないため使わない）"""
    timestamp = datetime.now(JST).strftime("%Y%m%d%H%M%S")
    return f"{category.lower()}-{timestamp}-{uuid.uuid4().hex[:6]}"


def post_to_d1(title, category, player_name, team_name, summary_lines, source_url, source_url_normalized):
    """Cloudflare D1（2026/8/4以降の本番投稿先）へ記事を書き込む。

    Cloudflare Pages Functions側のAPI（cloudflare/functions/api/articles.ts）にHTTP POSTする方式。
    D1書き込みの成否がその記事の「配信成功」を左右する（Livedoorへの投稿は従属的なバックグラウンド
    ミラーとして別途best-effortで行う。send_to_blog_background参照）。

    戻り値: 成功したslug文字列。失敗時はNone。
    """
    if not D1_INGEST_SECRET:
        print("エラー: D1_INGEST_SECRET が設定されていないため、D1への投稿をスキップします。")
        return None

    slug = generate_article_slug(category)
    payload = {
        "slug": slug,
        "category": category,
        "player_name": player_name,
        "team_name": team_name,
        "title": title,
        "summary_lines": summary_lines,
        "source_url": source_url,
        "source_url_normalized": source_url_normalized,
        "source_name": get_source_name(source_url),
        "published_at": datetime.now(JST).isoformat(),
    }

    try:
        response = requests.post(
            D1_INGEST_URL,
            json=payload,
            headers={"X-Ingest-Secret": D1_INGEST_SECRET},
            timeout=30,
        )
        if response.status_code in (200, 201):
            print(f"D1への投稿に成功しました: {title} (slug={slug})")
            return slug
        print(f"D1への投稿に失敗しました。ステータスコード: {response.status_code} / レスポンス: {response.text[:300]}")
        return None
    except Exception as e:
        print(f"D1投稿APIの呼び出しエラー: {e}")
        return None


def send_to_blog_background(subject, body_html, category, team_name=None, publish=True):
    """Livedoorへのバックグラウンド投稿。D1への本番投稿が成功した後にbest-effortで実行し、
    失敗してもメイン処理（配信成功の判定）には影響させない（2026/8/4のCloudflare移行後の位置づけ）。"""
    try:
        success = send_to_blog(subject, body_html, category, team_name=team_name, publish=publish)
        if not success:
            print("Livedoorへのバックグラウンド投稿に失敗しましたが、D1側は既に成功しているため処理は継続します。")
    except Exception as e:
        print(f"Livedoorへのバックグラウンド投稿中に例外が発生しましたが、D1側は既に成功しているため処理は継続します: {e}")


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
    # 正規化済みURLの集合。生のURL文字列同士の完全一致だけでなく、Google Newsのデコード先
    # （実際の記事URL）をトラッキングパラメータの差異を無視して比較するために使う。
    processed_normalized = {normalize_resolved_url(u) for u in processed_urls}
    print(f"現在の既読URL数: {len(processed_urls)}")

    urls_by_category = get_rss_urls_by_category()
    categories = list(urls_by_category.keys())
    # カテゴリの抽選順を毎回シャッフルする。サッカーはフィード・検索クエリ数が他競技より
    # 圧倒的に多いため、先にカテゴリ単位で抽選することで、フィード数に関わらず
    # 各カテゴリが均等に「その回の投稿候補」に選ばれるようにする。
    random.shuffle(categories)
    total_feeds = sum(len(v) for v in urls_by_category.values())
    print(f"巡回対象カテゴリ数: {len(categories)}件、フィード総数: {total_feeds}件 ※カテゴリ抽選順・フィード巡回順ともシャッフル済み")

    for category_hint in categories:
        feed_urls = list(urls_by_category[category_hint])
        random.shuffle(feed_urls)

        for rss_url in feed_urls:
            print(f"[{category_hint}] RSSフィードを巡回中: {rss_url}")
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
                norm_resolved = normalize_resolved_url(resolved_url)
                if resolved_url in processed_urls or norm_resolved in processed_normalized:
                    # 別の検索クエリ経由で既に処理済みだった同一記事なので、このリンクも既読化してスキップ
                    # （正規化比較により、片方の検索クエリでデコードが失敗していても、もう片方で
                    # 正常デコード済みの実URLと照合できるようにしている）
                    print(f"別ルートで既に処理済みの記事と判定したためスキップします: {resolved_url}")
                    save_processed_url(url)
                    processed_urls.add(url)
                    processed_normalized.add(normalize_resolved_url(url))
                    continue

                print(f"未着手の新規記事を発見しました: {entry.title}")
                raw_output = check_and_summarize_with_gemini(entry.title, entry.get("summary", ""))

                # レートリミット予防のため、AI呼び出し1回ごとに一定間隔を空ける
                time.sleep(API_CALL_INTERVAL_SECONDS)

                if not raw_output:
                    print("移籍・去就情報ではないためスキップ、またはAPIエラーです。")
                    save_processed_url(url)
                    processed_urls.add(url)
                    processed_normalized.add(normalize_resolved_url(url))
                    if resolved_url != url:
                        save_processed_url(resolved_url)
                        processed_urls.add(resolved_url)
                        processed_normalized.add(norm_resolved)
                    continue

                category, player_name, team_name, blog_title, summary_lines = parse_ai_output(raw_output)
                if not blog_title:
                    blog_title = entry.title
                if not summary_lines:
                    print("要約の抽出に失敗したためスキップします。")
                    save_processed_url(url)
                    processed_urls.add(url)
                    processed_normalized.add(normalize_resolved_url(url))
                    if resolved_url != url:
                        save_processed_url(resolved_url)
                        processed_urls.add(resolved_url)
                        processed_normalized.add(norm_resolved)
                    continue

                blog_body = build_blog_body(category, player_name, team_name, summary_lines, resolved_url)

                # 2026/8/4のCloudflare移行以降、D1への投稿成功を「配信成功」の判定基準にする。
                # Livedoorへの投稿はバックグラウンドのミラーとして、D1成功後にbest-effortで行う。
                d1_slug = post_to_d1(blog_title, category, player_name, team_name, summary_lines, resolved_url, norm_resolved)
                if d1_slug:
                    save_processed_url(url)
                    if resolved_url != url:
                        save_processed_url(resolved_url)
                    send_to_blog_background(blog_title, blog_body, category, team_name=team_name, publish=True)
                    print("1件の配信処理が正常終了したため、スクリプトを終了します。")
                    sys.exit(0)
                else:
                    print("D1への投稿に失敗したため、このURLは既読化せず次回リトライ対象として残します。")


if __name__ == "__main__":
    main()