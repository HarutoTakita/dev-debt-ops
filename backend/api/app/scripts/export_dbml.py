"""DB スキーマを DBML（ER 図）として docs/reference/schema.dbml に書き出す.

SQLModel/SQLAlchemy の ``SQLModel.metadata`` からテーブル・カラム・型・PK・FK・enum を走査して
DBML を生成する（dbdiagram.io / dbml-renderer で可視化可能）。``app.models`` を import すると
api + shared の全テーブルが metadata に登録される。DB もネットワークも不要。

実行（リポジトリルートから）::

    cd backend && uv run --directory api python -m app.scripts.export_dbml
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from sqlmodel import SQLModel

from app import models  # noqa: F401 -- 全 SQLModel テーブルを metadata に登録するため import する

REPO_ROOT = Path(__file__).resolve().parents[4]
OUT = REPO_ROOT / "docs" / "reference" / "schema.dbml"


def dbml_type(col: sa.Column) -> tuple[str, str | None]:
    """DBML 型名を返す（enum の場合は (enum名, enum定義) を返す）."""
    t = col.type
    if isinstance(t, sa.Enum):
        name = t.name or f"{col.table.name}_{col.name}_enum"
        values = "\n".join(f'  "{v}"' for v in t.enums)
        return name, f'Enum "{name}" {{\n{values}\n}}'
    mapping: list[tuple[type, str]] = [
        (sa.BigInteger, "bigint"),
        (sa.SmallInteger, "smallint"),
        (sa.Integer, "int"),
        (sa.Boolean, "boolean"),
        (sa.Text, "text"),
        (sa.Date, "date"),
        (sa.Float, "float"),
        (sa.Numeric, "decimal"),
        (sa.LargeBinary, "blob"),
        (sa.Uuid, "uuid"),
    ]
    for sa_type, name in mapping:
        if isinstance(t, sa_type):
            return name, None
    if isinstance(t, sa.DateTime):
        return ("timestamptz" if getattr(t, "timezone", False) else "timestamp"), None
    if isinstance(t, sa.String):
        return (f"varchar({t.length})" if t.length else "varchar"), None
    # JSON / JSONB / ARRAY など: SA の型名を小文字化してそのまま使う。
    return str(t).lower().split("(")[0].strip() or "text", None


def col_settings(col: sa.Column, single_pk: bool) -> str:
    """カラムの DBML 設定（pk / not null / unique / default / ref）を組み立てる."""
    parts: list[str] = []
    if single_pk and col.primary_key:
        parts.append("pk")
    if not col.nullable and not col.primary_key:
        parts.append("not null")
    if col.unique:
        parts.append("unique")
    # 単純なデフォルト（サーバデフォルトのリテラル）だけ載せる。
    sd = col.server_default
    if sd is not None and hasattr(sd, "arg"):
        text = getattr(sd.arg, "text", None) or (sd.arg if isinstance(sd.arg, str) else None)
        if text:
            parts.append(f"default: `{text}`")
    # FK 参照（多対一）。
    for fk in col.foreign_keys:
        parts.append(f"ref: > {fk.column.table.name}.{fk.column.name}")
    return f" [{', '.join(parts)}]" if parts else ""


def main() -> None:
    """SQLModel.metadata から DBML を生成し docs/reference/schema.dbml に書き出す."""
    md = SQLModel.metadata
    enums: dict[str, str] = {}
    tables_out: list[str] = []

    for table in md.sorted_tables:
        pk_cols = [c for c in table.columns if c.primary_key]
        single_pk = len(pk_cols) == 1
        lines = [f'Table "{table.name}" {{']
        for col in table.columns:
            typ, enum_def = dbml_type(col)
            if enum_def:
                enums[typ] = enum_def
            lines.append(f'  "{col.name}" {typ}{col_settings(col, single_pk)}')
        # 複合主キーは indexes ブロックで表現。
        if len(pk_cols) > 1:
            cols = ", ".join(f'"{c.name}"' for c in pk_cols)
            lines.append(f"  indexes {{\n    ({cols}) [pk]\n  }}")
        lines.append("}")
        tables_out.append("\n".join(lines))

    header = (
        "// DevDebtOps データベース ER 図（DBML）。\n"
        "// SQLModel.metadata から自動生成。dbdiagram.io に貼り付けるか dbml-renderer で可視化できる。\n"
        "// 再生成: cd backend && uv run --directory api python -m app.scripts.export_dbml\n\n"
        'Project devdebtops {\n  database_type: "PostgreSQL"\n'
        '  Note: "理解負債 × コード負債プラットフォームの DB スキーマ（api 所有・Alembic 管理）"\n}\n'
    )
    body = "\n\n".join(list(enums.values()) + tables_out)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(header + "\n" + body + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO_ROOT)} ({len(md.sorted_tables)} tables, {len(enums)} enums)")


if __name__ == "__main__":
    main()
