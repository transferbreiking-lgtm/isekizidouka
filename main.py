name: Auto Sports News Bot

on:
  schedule:
    - cron: '13 */2 * * *'   # 2時間おき（毎時13分、偶数時）に自動実行。正時ちょうどは混雑して遅延しやすいため意図的にずらしている
  workflow_dispatch:          # 管理画面から手動起動するためのボタン

permissions:
  contents: write   # processed_urls.txtをpushするために書き込み権限を明示的に付与

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.x'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install google-genai feedparser requests

      - name: Run main script
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          LIVEDOOR_BLOG_ID: ${{ secrets.LIVEDOOR_BLOG_ID }}
          LIVEDOOR_API_KEY: ${{ secrets.LIVEDOOR_API_KEY }}
        run: python main.py

      - name: Commit and Push processed_urls.txt
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@github.com"
          git add processed_urls.txt
          git diff --quiet && git diff --staged --quiet || (git commit -m "Update processed_urls.txt [skip ci]" && git push)
