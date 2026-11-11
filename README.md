# webexe - Web Page Extraction MCP Server

Webページにアクセスして情報を取得・抽出するための Model Context Protocol (MCP) サーバーです。
軽量な HTTP リクエストによる高速取得モードと、Playwright（ヘッドレス Chromium）による JavaScript 描画・SPA 対応ブラウザモードの両方をサポートしています。

---

## 主な機能

- **`fetch_web_page`**: Web ページの内容を取得し、Markdown / テキスト / HTML 形式で抽出します。
  - `mode`: `"fast"`（httpx による軽量・高速フェッチ）または `"browser"`（Playwright による動的描画）
  - `output_format`: `"markdown"`（推奨。LLM向け整形）、`"text"`（プレーンテキスト）、`"html"`（生HTML）
  - `selector`: CSS セレクタ（例: `article`, `#content`, `.post-body`）で特定ブロックのみを抽出可能
  - `wait_for_selector`: ブラウザモードでの要素描画待ちセレクタ
  - `max_length`: 長大なページに対する文字数上限の指定
- **`extract_page_links`**: ページ内のリンク（アンカーテキストと絶対URL）を一覧抽出（同一ドメイン絞り込み対応）。
- **`extract_page_tables`**: ページ内の `<table>` を検出し、Markdown テーブル形式で構造化抽出。
- **`search_web`**: WEB検索を実行してタイトル、URL、スニペットを取得します。
  - `engine`: `"google"`（ヘッドレスブラウザで Google ホームへアクセスし、検索窓に入力して検索結果を抽出）または `"duckduckgo"`（軽量・高速な直接検索）。デフォルトは `"google"`。
  - `fallback_to_duckduckgo`: Google側でCAPTCHAやブロック等の問題が起きた場合、自動的にDuckDuckGoへフォールバックして検索を継続します（デフォルト: True）。
  - `max_results`: 取得する検索結果の件数（デフォルト: 10）。
- **`search_page_content`**: ページ内から指定したキーワードを検索し、前後の文脈スニペットを抽出。

---

## インストールと必要要件

- **Python**: 3.13 以上
- **パッケージマネージャ**: [uv](https://github.com/astral-sh/uv)（推奨）

### 依存関係のセットアップ
```bash
# 依存関係の同期
uv sync

# Playwright ブラウザ（Chromium）のインストール（初回のみ）
uv run playwright install chromium
```

---

## MCP クライアントへの設定例

### 1. Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "webexe": {
      "command": "uv",
      "args": [
        "--directory",
        "D:\\dev\\webexe",
        "run",
        "webexe"
      ]
    }
  }
}
```

### 2. OpenCode (`~/.config/opencode/opencode.jsonc` または `opencode.json`)
```jsonc
{
  "mcp": {
    "webexe": {
      "type": "local",
      "command": [
        "uv",
        "run",
        "webexe"
      ],
      "cwd": "D:\\dev\\webexe",
      "enabled": true
    }
  }
}
```

確認コマンド:
```bash
opencode mcp list
```

### 3. Cursor / VS Code / Antigravity (`mcp.json`)
```json
{
  "mcpServers": {
    "webexe": {
      "command": "uv",
      "args": [
        "--directory",
        "D:\\dev\\webexe",
        "run",
        "webexe"
      ]
    }
  }
}
```

---

## 直接実行・テスト

MCP サーバーを手動で起動する場合：
```bash
uv run webexe
```

テストスクリプトの実行：
```bash
uv run python -c "import asyncio; from webexe.server import fetch_web_page; print(asyncio.run(fetch_web_page('https://example.com')))"
```
