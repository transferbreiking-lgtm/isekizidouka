"""
過去に投稿済みの記事（2026/8/17より前、articles_log.jsonlの運用開始前）を対象に、
main.py の articles_log.jsonl と同じスキーマでログを後付けするバックフィル専用スクリプト。
main.py / backfill_team_categories.py と同じディレクトリに置いて実行すること。

■ 背景
main.py は 2026/8/17（4-43）以降、投稿・記事アップデートのたびに構造化データ
（category/player_name/team_name/title/summary_lines/source_url/confidence）を
articles_log.jsonl へ永続保存するようになった。それ以前に投稿済みの記事（約2,000件超）
にはこのログが存在せず、TransferChronicle（Cloudflare Pages/D1版の派生サイト）で
過去記事データを流用する際、Livedoorの公開HTMLをスクレイピングし直す以外に手段が無かった。
本スクリプトはその「過去分の穴埋め」を行う（4-45参照）。

■ 復元できる項目・できない項目
- できる: article_id, permalink, category（サムネイルのalt属性 or 1つ目のcategoryタグから逆引き）,
          team_name（2つ目のcategoryタグ）, title, summary_lines（本文のli要素）,
          source_url（本文末尾の「情報元」リンク）, confidence（main.pyのextract_confidence_levelを
          summary_linesに適用して推定）, 元記事の投稿日時（atom:published）
- できない: player_name（記事HTML上に独立したフィールドとして残っておらず、機械的に確実な抽出が
            できないため空欄のままにする。Chronicle側で必要ならtitle/summary_linesのテキストから
            別途NLP/AI抽出すること）
- action フィールドは "backfilled" とし、main.py側が書き込む "created"/"updated" と区別できるようにする。

■ 使い方
1. まずは安全のため DRY RUN（実際にはファイルへ書き込まない・ログ出力のみ）で対象記事数を確認する
     python backfill_articles_log.py
2. 内容に問題なければ本番実行（実際に articles_log.jsonl へ追記する）
     DRY_RUN=false python backfill_articles_log.py

■ 環境変数
- LIVEDOOR_BLOG_ID / LIVEDOOR_API_KEY : main.py と共通（AtomPub GETに使用。AI呼び出しは行わないため
  GEMINI_API_KEY 等は不要）
- DRY_RUN : "false" を指定すると実際に書き込む（未指定時は "true" 扱いでログ出力のみ）
- MAX_ENTRIES : 1回の実行で処理する最大記事数（未指定なら無制限）

■ 再実行時の挙動
- 既に articles_log.jsonl に記録済みのarticle_id（main.py側の"created"/"updated"分も含む）は
  自動的にスキップするため、何度でも安全に再実行できる（重複追記の防止）。
"""

import os
import re
import sys
import json
import html
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests
from requests.auth import HTTPBasicAuth

# main.py の既存資産をそのまま再利用する
from main import (
    LIVEDOOR_BLOG_ID,
    LIVEDOOR_API_KEY,
    BLOG_BASE_URL,
    CATEGORY_LABELS,
    ARTICLES_LOG_FILE,
    extract_confidence_level,
)

CODE_BY_LABEL = {label: code for code, label in CATEGORY_LABELS.items()}

ATOM_NS = "http://www.w3.org/2005/Atom"
APP_NS = "http://www.w3.org/2007/app"
NS = {"atom": ATOM_NS, "app": APP_NS}

COLLECTION_ENDPOINT = f"https://livedoor.blogcms.jp/atompub/{LIVEDOOR_BLOG_ID}/article" if LIVEDOOR_BLOG_ID else None

DRY_RUN = os.environ.get("DRY_RUN", "true").strip().lower() != "false"
MAX_ENTRIES = os.environ.get("MAX_ENTRIES")
MAX_ENTRIES = int(MAX_ENTRIES) if MAX_ENTRIES else None

_LI_RE = re.compile(r"<li>(.*?)</li>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_THUMB_ALT_RE = re.compile(r'<img\s+src="[^"]*"\s+alt="([^"]*)"\s+class="article-thumbnail"')
_SOURCE_URL_RE = re.compile(r'情報元:\s*<a href="([^"]+)"')


def strip_html(raw_html):
    text = _TAG_RE.sub("", raw_html or "")
    return html.unescape(text).strip()


def load_existing_article_ids():
    """articles_log.jsonlに既に記録済みのarticle_idを読み込む（重複防止・再実行の安全性確保）"""
    if not os.path.exists(ARTICLES_LOG_FILE):
        return set()
    ids = set()
    with open(ARTICLES_LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("article_id"):
                ids.add(str(record["article_id"]))
    return ids


def fetch_all_entries():
    """AtomPubのコレクションエンドポイントを全ページ巡回し、<entry>要素のリストを返す。"""
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


def extract_article_id(entry_elem):
    """rel="edit"のリンクから記事ID（数字）を抽出する（main.pyのsend_to_blog()と同じ抽出方法）"""
    for link in entry_elem.findall("atom:link", NS):
        if link.get("rel") == "edit":
            match = re.search(r"/article/(\d+)", link.get("href", ""))
            if match:
                return match.group(1)
    return None


def extract_summary_and_source(body_html):
    """本文HTMLから要約箇条書き（<li>）と出典URLを抜き出す"""
    summary_lines = []
    for m in _LI_RE.finditer(body_html or ""):
        text = strip_html(m.group(1)).strip()
        if text:
            summary_lines.append(text)

    source_match = _SOURCE_URL_RE.search(body_html or "")
    source_url = source_match.group(1) if source_match else None

    return summary_lines, source_url


def extract_category_and_team(entry_elem, body_html):
    """1つ目の<category>（親カテゴリ）と2つ目の<category>（チーム名）を取り出す。
    サムネイルのalt属性が信頼できる場合はそちらを優先する（backfill_team_categories.pyと同じ方針）。"""
    categories = entry_elem.findall("atom:category", NS)
    first_label = categories[0].get("term") if categories else None
    team_name = categories[1].get("term") if len(categories) > 1 else None

    thumb_match = _THUMB_ALT_RE.search(body_html or "")
    thumb_alt_code = thumb_match.group(1) if thumb_match else None

    category_code = thumb_alt_code if thumb_alt_code in CATEGORY_LABELS else CODE_BY_LABEL.get(first_label)
    return category_code, team_name


def extract_published_at(entry_elem):
    """atom:publishedを優先し、無ければatom:updatedから投稿日時（ISO8601文字列）を取得する"""
    for tag in ("published", "updated"):
        elem = entry_elem.find(f"atom:{tag}", NS)
        if elem is not None and elem.text:
            return elem.text.strip()
    return datetime.now(timezone.utc).isoformat()


def build_record(entry_elem):
    article_id = extract_article_id(entry_elem)
    if not article_id:
        return None, None

    title_elem = entry_elem.find("atom:title", NS)
    title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""

    content_elem = entry_elem.find("atom:content", NS)
    body_html = content_elem.text if content_elem is not None else ""

    category_code, team_name = extract_category_and_team(entry_elem, body_html)
    summary_lines, source_url = extract_summary_and_source(body_html)
    confidence = extract_confidence_level(summary_lines) if summary_lines else "UNKNOWN"

    record = {
        "timestamp": extract_published_at(entry_elem),
        "action": "backfilled",
        "article_id": article_id,
        "permalink": f"{BLOG_BASE_URL}archives/{article_id}.html",
        "category": category_code,
        # 本文HTML上に独立したフィールドとして残っていないため復元不可。空欄のまま出力する。
        "player_name": None,
        "team_name": team_name,
        "title": title,
        "summary_lines": summary_lines,
        "source_url": source_url,
        "confidence": confidence,
    }
    return article_id, record


def main():
    if not all([LIVEDOOR_BLOG_ID, LIVEDOOR_API_KEY]):
        print("エラー: LIVEDOOR_BLOG_ID / LIVEDOOR_API_KEY が設定されていません。")
        sys.exit(1)

    print(f"モード: {'DRY RUN（articles_log.jsonlへは書き込みません）' if DRY_RUN else '本番実行（articles_log.jsonlへ追記します）'}")

    existing_ids = load_existing_article_ids()
    print(f"既にarticles_log.jsonlに記録済みの記事数（スキップ対象）: {len(existing_ids)}")

    entries = fetch_all_entries()
    print(f"取得した全記事数: {len(entries)}")

    processed_count = 0
    skipped_existing = 0
    written_count = 0

    fh = None if DRY_RUN else open(ARTICLES_LOG_FILE, "a", encoding="utf-8")

    try:
        for entry_elem in entries:
            if MAX_ENTRIES is not None and processed_count >= MAX_ENTRIES:
                print(f"MAX_ENTRIES（{MAX_ENTRIES}件）に達したため処理を終了します。")
                break

            article_id, record = build_record(entry_elem)
            if not article_id:
                continue

            if article_id in existing_ids:
                skipped_existing += 1
                continue

            processed_count += 1
            print(f"[{processed_count}] バックフィル対象: article_id={article_id} / {record['title']}")

            if DRY_RUN:
                print(f"  → [DRY RUN] {json.dumps(record, ensure_ascii=False)}")
            else:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                written_count += 1
                existing_ids.add(article_id)
    finally:
        if fh:
            fh.close()

    print(f"完了。対象記事数: {processed_count} / 既存スキップ: {skipped_existing} / 書き込み: {written_count}")


if __name__ == "__main__":
    main()
