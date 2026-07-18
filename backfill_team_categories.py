"""
過去に投稿済みの記事に対して、下記3つを後付け・自動修正する専用スクリプト。
main.py と同じディレクトリに置いて実行すること（main.py の資産をそのまま再利用する）。

  1. チーム別カテゴリタグ（2つ目の<category>）の後付け
     - 対象: <category>が1つしか付いていない記事（＝チームタグ未付与の記事）
     - タイトル・本文をAIに読ませてチーム名を再抽出する
     - 記事本文側の変更は行わない。2つ目のカテゴリを送信するだけで、記事上部の
       赤バッジ（<$ArticleCategory1$>の右隣に並ぶ<$ArticleCategory2$>）が自動的に表示される。

  2. 記事下部の「同カテゴリの記事一覧」バナーの同期
     - 親カテゴリ（競技カテゴリ）の記事一覧ページへ飛べるバナーを、常に最新の状態に揃える。
     - 旧仕様（チーム別リンクだった時期）のバナーが残っている記事は、親カテゴリへのリンクに置き換える。
     - バナー自体が無い古い記事には、ad-sectionの直前に新規挿入する。

  3. サムネイル（バナー）画像の同期
     - main.py の THUMBNAIL_IMAGES 辞書を差し替えた後、過去記事の <img> タグが古いURLの
       ままになる問題を修正する（既存タグのsrcだけを差し替え）。
     - サムネイル自体が存在しない古い記事には、article-outerの直後に新規挿入する。
     - カテゴリコードは、既存の<img alt="...">があればそれを優先し、無ければ記事の
       1つ目の<category>（親カテゴリ）のラベルから逆引きする。
     - AI呼び出しは発生しないため無料枠を消費しない。何度でも安全に再実行できる。

■ 使い方
1. まずは安全のため DRY RUN（実際には更新しない・ログ出力のみ）で対象記事と修正内容を確認する
     python backfill_team_categories.py
2. 内容に問題なければ本番実行（実際にライブドアへPUTして更新する）
     DRY_RUN=false python backfill_team_categories.py

■ 環境変数
- GEMINI_API_KEY / OPENROUTER_API_KEY / LIVEDOOR_BLOG_ID / LIVEDOOR_API_KEY : main.py と共通
- DRY_RUN : "false" を指定すると実際に更新を実行する（未指定時は "true" 扱いでログ出力のみ）
- MAX_ENTRIES : 1回の実行で処理する最大記事数（未指定なら無制限）

■ 再実行時の挙動
- チームタグ付与が「試行済み」のentry IDは backfill_processed.txt に記録し、以後AI再抽出をスキップする
  （チーム名が特定できなかった記事も、無駄なAI再呼び出しを避けるため記録する）
- バナー・サムネイルの同期は毎回「今のmain.py側の辞書」と実際のHTMLを比較するだけなので、
  ズレがなければ自動的に何もしない。ログファイルへの記録は不要（辞書を差し替えるたびに何度でも実行してよい）
"""

import os
import re
import sys
import time
import html
import xml.etree.ElementTree as ET

import requests
from requests.auth import HTTPBasicAuth

# main.py の既存資産（環境変数読み込み・カテゴリ辞書・サムネイル辞書・AI呼び出し）を再利用する
from main import (
    LIVEDOOR_BLOG_ID,
    LIVEDOOR_API_KEY,
    GEMINI_API_KEY,
    THUMBNAIL_IMAGES,
    CATEGORY_LABELS,
    build_team_archive_url,
    call_gemini_with_retry,
    call_openrouter_fallback,
)

# ラベル（日本語カテゴリ名）→ 内部カテゴリコードの逆引き辞書（例: "サッカー" → "SOCCER"）
CODE_BY_LABEL = {label: code for code, label in CATEGORY_LABELS.items()}

ATOM_NS = "http://www.w3.org/2005/Atom"
APP_NS = "http://www.w3.org/2007/app"
NS = {"atom": ATOM_NS, "app": APP_NS}
ET.register_namespace("", ATOM_NS)
ET.register_namespace("app", APP_NS)

COLLECTION_ENDPOINT = f"https://livedoor.blogcms.jp/atompub/{LIVEDOOR_BLOG_ID}/article" if LIVEDOOR_BLOG_ID else None

DRY_RUN = os.environ.get("DRY_RUN", "true").strip().lower() != "false"
MAX_ENTRIES = os.environ.get("MAX_ENTRIES")
MAX_ENTRIES = int(MAX_ENTRIES) if MAX_ENTRIES else None

BACKFILL_LOG_FILE = "backfill_processed.txt"
API_CALL_INTERVAL_SECONDS = 4

_TAG_RE = re.compile(r"<[^>]+>")
_THUMB_IMG_RE = re.compile(r'<img\s+src="([^"]*)"\s+alt="([^"]*)"\s+class="article-thumbnail"')
# 記事下バナー（旧仕様のチーム別リンク含む）を丸ごと検出・置換するための正規表現
_RELATED_BANNER_RE = re.compile(
    r'\s*<div class="related-team-section"[^>]*>.*?</div>',
    re.DOTALL,
)


def strip_html(raw_html):
    """記事本文HTMLからタグを除去し、AIに読ませるためのプレーンテキストに変換する"""
    text = _TAG_RE.sub(" ", raw_html or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def get_thumbnail_info(body_html):
    """本文HTML中のサムネイル<img>タグから (現在のsrc, カテゴリコード) を取り出す。見つからなければ (None, None)"""
    m = _THUMB_IMG_RE.search(body_html or "")
    if not m:
        return None, None
    return m.group(1), m.group(2)


def fix_thumbnail_src(body_html, new_src, category_code):
    """サムネイル<img>タグのsrcだけを新しいURLに差し替える（alt等の他属性はそのまま維持）"""
    def _replace(m):
        return f'<img src="{new_src}" alt="{category_code}" class="article-thumbnail"'
    return _THUMB_IMG_RE.sub(_replace, body_html, count=1)


def sync_thumbnail(body_html, category_code):
    """本文内のサムネイル画像を、指定カテゴリコードの現在の正しいURLに揃える。
    既存タグがあればsrcだけを差し替え、無ければ article-outer の直後に新規挿入する。
    変更が無ければ (body_html, False) を返す。"""
    expected_url = THUMBNAIL_IMAGES.get(category_code)
    if not expected_url:
        return body_html, False

    current_src, _ = get_thumbnail_info(body_html)
    if current_src == expected_url:
        return body_html, False

    if current_src:
        return fix_thumbnail_src(body_html, expected_url, category_code), True

    marker = '<div class="article-outer">'
    if marker not in body_html:
        return body_html, False  # 想定外の構造なので変更しない

    img_tag = (
        f'\n        <img src="{expected_url}" alt="{category_code}" class="article-thumbnail" '
        f'style="max-width:100%; width:100%; height:auto; display:block; border:1px solid #333;" />'
    )
    return body_html.replace(marker, marker + img_tag, 1), True


def build_category_banner_html(category_label, category_archive_url):
    """main.py の build_blog_body() と同一のHTML構造でバナーブロックを組み立てる"""
    return (
        '\n        <div class="related-team-section" '
        'style="margin-top:16px; padding:10px 14px; background:#1a1a1c; border-left:3px solid #e4002b;">\n'
        f'            <a href="{category_archive_url}" style="color:#e4002b; text-decoration:none; '
        f'font-weight:bold;">📌 {category_label}の記事一覧はこちら »</a>\n'
        '        </div>'
    )


def sync_category_banner(body_html, category_label, category_archive_url):
    """本文内の「同カテゴリの記事一覧はこちら」バナーを、現在の親カテゴリを指すものに揃える。
    既存の（旧仕様のチーム別リンク含む）バナーがあれば置き換え、無ければ ad-section の直前に新規挿入する。
    変更が無ければ (body_html, False) を返す。"""
    expected_html = build_category_banner_html(category_label, category_archive_url)

    if expected_html.strip() in body_html:
        return body_html, False  # 既に最新の状態

    if _RELATED_BANNER_RE.search(body_html):
        updated = _RELATED_BANNER_RE.sub(expected_html, body_html, count=1)
        return updated, True

    marker = '<div class="ad-section">'
    if marker not in body_html:
        return body_html, False  # 想定外の構造なので変更しない

    updated = body_html.replace(marker, expected_html + "\n        " + marker, 1)
    return updated, True


def load_backfilled_ids():
    """既にチームタグ付与を試行済みのentry IDセットを読み込む"""
    if not os.path.exists(BACKFILL_LOG_FILE):
        return set()
    with open(BACKFILL_LOG_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def save_backfilled_id(entry_id):
    """チームタグ付与を試行済みのentry IDを追記保存する"""
    with open(BACKFILL_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry_id + "\n")


def fetch_all_entries():
    """AtomPubのコレクションエンドポイントを全ページ巡回し、<entry>要素のリストを返す。
    rel="next" のリンクが無くなるまでページングする。"""
    entries = []
    url = COLLECTION_ENDPOINT
    auth = HTTPBasicAuth(LIVEDOOR_BLOG_ID, LIVEDOOR_API_KEY)

    while url:
        try:
            response = requests.get(url, auth=auth, timeout=30)
        except Exception as e:
            print(f"フィード取得中にエラーが発生しました: {e}")
            break

        if response.status_code != 200:
            print(f"フィード取得に失敗しました。ステータスコード: {response.status_code} / {response.text[:300]}")
            break

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            print(f"フィードのXMLパースに失敗しました: {e}")
            break

        page_entries = root.findall("atom:entry", NS)
        entries.extend(page_entries)
        print(f"フィード1ページ分を取得しました（{len(page_entries)}件） / 累計{len(entries)}件")

        next_link = None
        for link in root.findall("atom:link", NS):
            if link.get("rel") == "next":
                next_link = link.get("href")
                break
        url = next_link

    return entries


def extract_team_name(title, body_text):
    """過去記事のタイトル・本文からAIでチーム名を再抽出する。main.pyのAIモデル呼び出しをそのまま再利用する。"""
    prompt = f"""
あなたはプロのスポーツ編集者です。以下は過去に投稿されたスポーツ移籍ニュース記事です。
この記事の中心となるチーム・クラブ名を1つだけ特定してください。

【記事タイトル】: {title}
【記事本文】: {body_text[:1500]}

■ 出力ルール
- 移籍の場合は移籍先チームを優先してください。移籍先が未定・不明な場合は移籍元チームでも構いません。
- 正式名称または日本のメディアで一般的に使われる表記で、20文字以内で簡潔に記載してください（例: レアル・マドリード、読売ジャイアンツ、レイカーズ）。
- 特定のチームに紐づかない話題の場合は、他の文言を一切付けず「不明」とだけ出力してください。
- 出力はチーム名（または「不明」）の1行のみとし、説明・前置き・記号は一切不要です。
"""
    result = call_gemini_with_retry(prompt)
    if result is None:
        print("Geminiでの抽出に失敗したため、OpenRouterへフォールバックします。")
        result = call_openrouter_fallback(prompt)

    if result is None:
        return None

    team_name = result.strip().split("\n")[0].strip()
    if team_name in ("", "不明", "None") or len(team_name) > 30:
        return None
    return team_name.replace("\n", "").replace("/", "・").strip()


def update_entry(entry_elem, team_name=None, new_body_html=None):
    """entry要素を必要な分だけ更新してPUTする。
    team_name     : 指定があれば2つ目の<category>を追加する（本文は変更しない。上部バッジは
                     <$ArticleCategory2$>がテンプレート側で自動表示するため）。
    new_body_html : 指定があれば本文全体をこの内容で置き換える（サムネイル・バナー同期済みのHTML）。
    どちらも指定が無ければ何もせず True を返す（呼び出し元のフィルタ漏れに対する保険）。"""
    edit_href = None
    for link in entry_elem.findall("atom:link", NS):
        if link.get("rel") == "edit":
            edit_href = link.get("href")
            break

    if not edit_href:
        print("編集用URL（rel=edit）が見つからなかったためスキップします。")
        return False

    changed = False

    if team_name:
        ET.SubElement(entry_elem, "{%s}category" % ATOM_NS, attrib={
            "scheme": f"https://livedoor.blogcms.jp/atompub/{LIVEDOOR_BLOG_ID}/category",
            "term": team_name,
        })
        changed = True

    if new_body_html is not None:
        content_elm = entry_elem.find("atom:content", NS)
        if content_elm is not None:
            content_elm.text = new_body_html
            changed = True

    if not changed:
        return True  # このentryには実質的な変更なし（呼び出し元のフィルタ漏れ対策）

    if DRY_RUN:
        print(f"[DRY RUN] 更新をスキップ（実際には送信しません）: team={team_name} / body_changed={new_body_html is not None} / edit_href={edit_href}")
        return True

    xml_body = '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(entry_elem, encoding="unicode")
    headers = {"Content-Type": "application/atom+xml;type=entry;charset=utf-8"}

    try:
        response = requests.put(
            edit_href,
            data=xml_body.encode("utf-8"),
            headers=headers,
            auth=HTTPBasicAuth(LIVEDOOR_BLOG_ID, LIVEDOOR_API_KEY),
            timeout=30,
        )
        if response.status_code in (200, 204):
            print(f"更新に成功しました: team={team_name} / body_changed={new_body_html is not None}")
            return True
        print(f"更新に失敗しました。ステータスコード: {response.status_code} / レスポンス: {response.text[:300]}")
        return False
    except Exception as e:
        print(f"AtomPub PUT 実行エラー: {e}")
        return False


def main():
    if not all([LIVEDOOR_BLOG_ID, LIVEDOOR_API_KEY]):
        print("エラー: LIVEDOOR_BLOG_ID / LIVEDOOR_API_KEY が設定されていません。")
        sys.exit(1)
    if not GEMINI_API_KEY:
        print("エラー: GEMINI_API_KEY が設定されていません。")
        sys.exit(1)

    print(f"モード: {'DRY RUN（変更は送信しません）' if DRY_RUN else '本番実行（実際に更新します）'}")

    backfilled_ids = load_backfilled_ids()
    print(f"チームタグ付与を試行済みの記事数（記録上）: {len(backfilled_ids)}")

    entries = fetch_all_entries()
    print(f"取得した全記事数: {len(entries)}")

    processed_count = 0
    updated_count = 0

    for entry_elem in entries:
        if MAX_ENTRIES is not None and processed_count >= MAX_ENTRIES:
            print(f"MAX_ENTRIES（{MAX_ENTRIES}件）に達したため処理を終了します。")
            break

        id_elem = entry_elem.find("atom:id", NS)
        entry_id = id_elem.text.strip() if id_elem is not None and id_elem.text else None
        if not entry_id:
            continue

        categories = entry_elem.findall("atom:category", NS)
        content_elm = entry_elem.find("atom:content", NS)
        body_html = content_elm.text if content_elm is not None else ""

        # 親カテゴリ（1つ目の<category>）のラベル・内部コードを特定する
        first_category_label = categories[0].get("term") if categories else None
        current_thumb_src, thumb_alt_code = get_thumbnail_info(body_html)
        # サムネイルのalt属性があればそれを優先（最も信頼できる）。無ければラベルから逆引きする。
        category_code = thumb_alt_code or CODE_BY_LABEL.get(first_category_label)
        category_label = CATEGORY_LABELS.get(category_code, first_category_label)

        # ① チームタグの後付けが必要か（未試行 かつ カテゴリが1個のみ）
        needs_team = entry_id not in backfilled_ids and len(categories) < 2

        # ② サムネイル画像の同期（ズレ修正／未設置記事への新規設置の両対応）
        body_after_thumb, thumb_changed = (
            sync_thumbnail(body_html, category_code) if category_code else (body_html, False)
        )

        # ③ 記事下バナー（親カテゴリの記事一覧）の同期
        body_after_banner, banner_changed = (
            sync_category_banner(body_after_thumb, category_label, build_team_archive_url(category_label))
            if category_label else (body_after_thumb, False)
        )

        needs_body_update = thumb_changed or banner_changed

        if not needs_team and not needs_body_update:
            continue  # このentryは対応不要

        title_elem = entry_elem.find("atom:title", NS)
        title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
        if not title:
            continue

        processed_count += 1

        team_name = None
        if needs_team:
            print(f"[{processed_count}] チーム名抽出中: {title}")
            team_name = extract_team_name(title, strip_html(body_html))
            time.sleep(API_CALL_INTERVAL_SECONDS)
            if team_name:
                print(f"  → 抽出結果: {team_name}")
            else:
                print("  → チーム名を特定できなかったため、チームタグの付与は見送ります。")

        if thumb_changed:
            print(f"[{processed_count}] サムネイル画像を同期します: {title}（category={category_code}）")
        if banner_changed:
            print(f"[{processed_count}] 記事下バナーを同期します: {title}（{category_label}の記事一覧へ）")

        success = update_entry(
            entry_elem,
            team_name=team_name,
            new_body_html=body_after_banner if needs_body_update else None,
        )

        if success:
            updated_count += 1
            if needs_team and not DRY_RUN:
                # チーム名が特定できた/できなかったに関わらず「試行済み」として記録し、
                # 次回実行時に同じ記事へ無駄なAI呼び出しを繰り返さないようにする。
                # DRY RUN中は実際には何も更新していないため、ここで記録してはいけない
                # （記録してしまうと、その後の本番実行時に「試行済み」と誤判定され、
                #   チームタグが一切送信されなくなるバグになる）。
                save_backfilled_id(entry_id)
                backfilled_ids.add(entry_id)

        time.sleep(API_CALL_INTERVAL_SECONDS)

    print(f"完了。対応対象記事数: {processed_count} / 更新成功: {updated_count}")


if __name__ == "__main__":
    main()
