### 作成時のプロンプト
```
WEBページにアクセスして情報をとってくるMCPツールを作成してください
```
```
WEB検索機能を追加できますか？
```

### 再現性のあるプロンプト
```
PythonとMCP SDKを用いて、Webページの取得・情報抽出およびWeb検索を行うMCPサーバーを作成し、テスト実行まで完了してください。

### 1. 技術スタック・環境
- 言語・ツール: Python (>=3.13), パッケージ管理には `uv` を使用
- 依存ライブラリ:
  - `mcp[cli]` (Model Context Protocol 公式SDK, v2.x対応 `mcp.server.mcpserver.MCPServer`)
  - `httpx` (軽量・高速なHTTPリクエスト)
  - `playwright` (JavaScript描画・SPA・動的サイト対応のChromium)
  - `beautifulsoup4`, `markdownify` (HTMLパースおよびMarkdown変換)
  - `duckduckgo-search` (軽量Web検索用)

### 2. 実装要件（提供するMCPツール）
以下の5つのツールを定義してください：

1. `fetch_web_page`:
   - URLからWebページの内容を取得し、Markdown / プレーンテキスト / 生HTMLの指定形式で出力。
   - `mode`: `"fast"` (httpxによる高速取得) と `"browser"` (Playwrightによる動的描画取得) の切り替えに対応。
   - CSSセレクタ指定 (`selector`) による特定ブロックの絞り込み、ブラウザ描画待機 (`wait_for_selector`)、コンテキスト上限防止のための最大文字数制限 (`max_length`) を実装。

2. `search_web`:
   - Web検索を実行してタイトル、URL、スニペットを取得。
   - `engine`: `"google"` (PlaywrightでGoogleホームへアクセスし、検索窓にキーワードを入力して検索結果を抽出) と `"duckduckgo"` (軽量直接検索) に対応。
   - Google側でボット検出（CAPTCHA）等が発生した場合は自動的にDuckDuckGoへフォールバックすること。

3. `extract_page_links`:
   - ページ内のリンク（アンカーテキストと絶対URL）を一覧抽出（同一ドメイン内のみのフィルタリングに対応）。

4. `extract_page_tables`:
   - ページ内の `<table>` を検出し、Markdownテーブル形式で構造化抽出。

5. `search_page_content`:
   - ページ内から指定したキーワードを検索し、前後の文脈を含んだ抜粋スニペットを抽出。

### 3. プロジェクト構成と動作確認
- `uv init` でプロジェクトを作成し、`pyproject.toml` の `[project.scripts]` にCLIエントリーポイントを定義すること。
- Playwrightのブラウザ (`uv run playwright install chromium`) のインストールまで実行すること。
- 各ツールが正常に動作することをスクリプト等でテスト実行し、正しく結果が返ることを確認すること。
- 使い方・各ツールの仕様をまとめた `README.md` を作成すること。
```
