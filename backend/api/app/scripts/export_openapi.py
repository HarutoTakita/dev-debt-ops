"""FastAPI アプリの OpenAPI スキーマを docs/reference/openapi.json に書き出す (API ドキュメント生成).

実行（リポジトリルートから）::

    cd backend && uv run --directory api python -m app.scripts.export_openapi

スキーマはルート定義から純粋に構築されるため、DB もネットワークも不要。ルートやスキーマを変更したら
再実行して docs 側を更新する（CI ではなく手動更新でよい軽量ドキュメント）。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app

# backend/api/app/scripts/export_openapi.py -> リポジトリルートは parents[4]。
REPO_ROOT = Path(__file__).resolve().parents[4]
OUT_DIR = REPO_ROOT / "docs" / "reference"


def main() -> None:
    """OpenAPI スキーマを JSON として docs/reference/ に書き出す."""
    schema = app.openapi()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    json_path = OUT_DIR / "openapi.json"
    json_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {json_path.relative_to(REPO_ROOT)} ({len(schema.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
