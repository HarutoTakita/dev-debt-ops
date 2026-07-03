"""Root-level scaffolding files served for the guest-demo repo browser (richer-demo issue).

The demo project (``devdebtops/sample-shop``) is GitHub-less: its file tree and file contents are served
from seeded rows (see the demo branches in ``app.api.v1.github``). Those rows only cover analysed source
under ``src/`` — each has a ``CodeDebt``. To make the file browser look like a real repository (README,
manifests, CI, Docker, tests, docs), this module provides realistic **root / non-src** files as a static,
DB-free source.

These files intentionally carry **no analysis rows** (no CodeDebt / FileKc): they show up in the tree as
clean, openable files and never pollute the Overview scatter, the Galaxy, or the debt list. Keyed by
repo-relative path → file content.
"""

from __future__ import annotations

# The demo repo these scaffolding files belong to (mirrors seed_demo's DEMO_REPO_OWNER / DEMO_REPO_NAME).
_DEMO_OWNER = "devdebtops"
_DEMO_REPO = "sample-shop"


_README = """\
# sample-shop

小規模な EC ストアのサンプルリポジトリ。カート・決済・在庫・配送・通知までの一連のフローを備える。

## 構成
- `src/checkout/` — カート・決済確定・クーポン
- `src/auth/` — ログイン・セッション・OAuth・JWT
- `src/catalog/` — 商品検索・カタログ
- `src/inventory/` — 在庫・倉庫・引当
- `src/shipping/` — 配送・追跡
- `src/notifications/` — メール・プッシュ通知

## 技術スタック
- Backend: Python 3.13 / FastAPI / SQLModel / PostgreSQL
- Frontend: SvelteKit / TypeScript
- Infra: Docker / Google Cloud Run / GitHub Actions

## 開発
```bash
make dev        # api + db を起動
make test       # pytest
make lint       # ruff / prettier
```
"""

_PYPROJECT = """\
[project]
name = "sample-shop"
version = "0.3.1"
description = "Sample e-commerce store"
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.115",
    "sqlmodel>=0.0.22",
    "asyncpg>=0.29",
    "pydantic>=2.9",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "ruff>=0.6"]

[tool.ruff]
line-length = 120
target-version = "py313"
"""

_PACKAGE_JSON = """\
{
  "name": "sample-shop-web",
  "version": "0.3.1",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite dev",
    "build": "vite build",
    "check": "svelte-check --tsconfig ./tsconfig.json",
    "lint": "prettier --check . && eslint ."
  },
  "devDependencies": {
    "@sveltejs/kit": "^2.7.0",
    "svelte": "^5.0.0",
    "typescript": "^5.6.0",
    "vite": "^5.4.0"
  }
}
"""

_DOCKER_COMPOSE = """\
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_USER: shop
      POSTGRES_PASSWORD: shop
      POSTGRES_DB: shop
    ports:
      - "5432:5432"
  api:
    build: .
    depends_on:
      - db
    environment:
      DATABASE_URL: postgresql+asyncpg://shop:shop@db:5432/shop
    ports:
      - "8000:8000"
"""

_DOCKERFILE = """\
FROM python:3.13-slim AS runtime
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY src ./src
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
"""

_CI = """\
name: CI

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:17
        env:
          POSTGRES_PASSWORD: shop
        ports:
          - 5432:5432
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -e ".[dev]"
      - run: ruff check src
      - run: pytest -q
"""

_ENV_EXAMPLE = """\
# アプリ設定（.env にコピーして使用）
DATABASE_URL=postgresql+asyncpg://shop:shop@localhost:5432/shop
SECRET_KEY=change-me
# 外部連携
STRIPE_API_KEY=
CARRIER_API_URL=https://api.carrier.example/v1
SMTP_URL=smtp://localhost:1025
"""

_MAKEFILE = """\
.PHONY: dev test lint fmt

dev:
\tdocker compose up

test:
\tpytest -q

lint:
\truff check src && prettier --check .

fmt:
\truff format src && prettier --write .
"""

_ALEMBIC_INI = """\
[alembic]
script_location = migrations
sqlalchemy.url = postgresql+asyncpg://shop:shop@localhost:5432/shop

[loggers]
keys = root,sqlalchemy,alembic
"""

_TEST_CHECKOUT = """\
import pytest

from src.checkout.payment import confirm_payment


def test_confirm_payment_rolls_back_on_mark_paid_failure(fake_order, active_user):
    # mark_paid が失敗したら課金は取り消され、成功扱いにならないこと。
    result = confirm_payment(fake_order, active_user)
    assert result is False


@pytest.mark.parametrize("total", [0, -1])
def test_confirm_payment_rejects_non_positive_total(total, fake_order, active_user):
    fake_order.total = total
    # 合計が 0 以下なら課金してはいけない（現状は True を返す既知の不具合）。
    assert confirm_payment(fake_order, active_user) is not None
"""

_CONFTEST = """\
import pytest


@pytest.fixture
def active_user():
    class User:
        is_active = True
        card = "tok_visa"
    return User()


@pytest.fixture
def fake_order():
    class Order:
        total = 1200
        email = "buyer@example.com"
    return Order()
"""

_ARCHITECTURE = """\
# アーキテクチャ概要

## リクエストの流れ
1. SvelteKit フロントが `/api` を叩く
2. FastAPI がルーティングし、サービス層がドメインロジックを実行
3. SQLModel 経由で PostgreSQL に永続化

## 注文フロー（要点）
- カート → 在庫引当（`inventory`）→ 決済確定（`checkout/payment`）→ 出荷（`shipping`）→ 通知（`notifications`）
- 決済と在庫は密結合。引当と課金の順序・冪等性が最重要ポイント。

## 既知の負債
- `checkout/payment.py`: 深いネスト（複雑度が高い）と成功判定の穴
- `catalog/search.ts`: フィルタ生成の重複
- `auth/session.py`: 未使用の旧セッション検証（dead code）
"""

_GITIGNORE = """\
__pycache__/
*.pyc
.venv/
node_modules/
build/
.env
.env.*
!.env.example
*.log
"""

_LICENSE = """\
MIT License

Copyright (c) 2026 devdebtops

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
"""


# Repo-relative path → file content. Paths deliberately include nested dirs (.github/workflows, tests,
# docs) so the file tree shows real folders at the repository root alongside ``src/``.
SCAFFOLD_FILES: dict[str, str] = {
    "README.md": _README,
    "pyproject.toml": _PYPROJECT,
    "package.json": _PACKAGE_JSON,
    "docker-compose.yml": _DOCKER_COMPOSE,
    "Dockerfile": _DOCKERFILE,
    ".github/workflows/ci.yml": _CI,
    ".env.example": _ENV_EXAMPLE,
    "Makefile": _MAKEFILE,
    "alembic.ini": _ALEMBIC_INI,
    "tests/test_checkout.py": _TEST_CHECKOUT,
    "tests/conftest.py": _CONFTEST,
    "docs/architecture.md": _ARCHITECTURE,
    ".gitignore": _GITIGNORE,
    "LICENSE": _LICENSE,
}


def scaffold_for(owner: str, repo: str) -> dict[str, str]:
    """Return the scaffolding files for a repo, or empty for non-demo repos.

    Only the primary demo repo (``devdebtops/sample-shop``) gets scaffolding; the metadata-only extra
    demo projects have empty trees and stay that way.
    """
    if (owner, repo) == (_DEMO_OWNER, _DEMO_REPO):
        return SCAFFOLD_FILES
    return {}
