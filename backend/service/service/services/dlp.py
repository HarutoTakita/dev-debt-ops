"""Cloud DLP (Sensitive Data Protection) による PII de-identification（issue 296）.

``DLP_ENABLED=true`` のときだけ使う（既定 false）。``deidentifyContent`` で**保守的な高確度 infoType**
（メール/電話/クレジットカード/IP/日本のマイナンバー・銀行口座/IBAN/SSN）を検出し、infoType 名で置換する。
ステートレス（DLP 側にデータを保存しない）。認証は既存 Vertex/ADC と同じ service SA の ADC（`roles/dlp.user`
が必要 — infra/gcp/iam.tf）。

``deidentifyContent`` の非構造化コンテンツには ~0.5MB/req の上限があるため、大きなテキストは行境界で
バイト上限ごとに分割して呼ぶ。失敗（未有効・権限不足・タイムアウト・ライブラリ未導入等）は例外として
伝播させ、呼び出し側（``secret_redaction.deidentify``）がローカルのルールベースへフォールバックする。
"""

from collections.abc import Iterable
from functools import lru_cache

from google.cloud import dlp_v2

from service import config

# 保守的な高確度 infoType のみ。氏名(PERSON_NAME)・住所(STREET_ADDRESS)はコード中の識別子を誤マスク
# しやすいため含めない（issue 296 の方針）。
_INFO_TYPES: tuple[str, ...] = (
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD_NUMBER",
    "IP_ADDRESS",
    "IBAN_CODE",
    "JAPAN_INDIVIDUAL_NUMBER",
    "JAPAN_BANK_ACCOUNT",
    "US_SOCIAL_SECURITY_NUMBER",
)
# DLP の content 上限（~0.5MB）に余裕を持たせたチャンクサイズ（bytes）。
_MAX_CHUNK_BYTES = 400_000


@lru_cache(maxsize=1)
def _client() -> dlp_v2.DlpServiceAsyncClient:
    """DLP 非同期クライアント（ADC）。1 度だけ生成して使い回す."""
    return dlp_v2.DlpServiceAsyncClient()


def _inspect_config() -> dlp_v2.InspectConfig:
    return dlp_v2.InspectConfig(info_types=[dlp_v2.InfoType(name=name) for name in _INFO_TYPES])


def _deidentify_config() -> dlp_v2.DeidentifyConfig:
    # 検出した各 infoType を、その infoType 名（例: EMAIL_ADDRESS）で置換する。
    return dlp_v2.DeidentifyConfig(
        info_type_transformations=dlp_v2.InfoTypeTransformations(
            transformations=[
                dlp_v2.InfoTypeTransformations.InfoTypeTransformation(
                    primitive_transformation=dlp_v2.PrimitiveTransformation(
                        replace_with_info_type_config=dlp_v2.ReplaceWithInfoTypeConfig()
                    )
                )
            ]
        )
    )


def _chunks(text: str) -> list[str]:
    """~0.5MB 上限に収まるよう、行境界でバイト単位に分割する（単一チャンクなら 1 要素）."""
    if len(text.encode("utf-8")) <= _MAX_CHUNK_BYTES:
        return [text]
    out: list[str] = []
    cur: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        b = len(line.encode("utf-8"))
        if size + b > _MAX_CHUNK_BYTES and cur:
            out.append("".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += b
    if cur:
        out.append("".join(cur))
    return out


async def deidentify_pii(text: str, *, allowlist: Iterable[str] = ()) -> tuple[str, int]:
    """Cloud DLP で ``text`` の PII をマスクする。``(masked_text, 件数)`` を返す.

    ``allowlist``（owner/repo/branch 等）は保守的 infoType では衝突しにくいため現状 DLP 側の除外には
    使わない（シグネチャ互換のため受け取る）。件数は DLP のオーバービュー統計から集計する（advisory）。
    失敗時は例外を送出し、呼び出し側がフォールバックする。
    """
    _ = allowlist  # 予約（将来 DLP の exclusion rule に使用可能）
    if not text:
        return text, 0
    parent = f"projects/{config.google_cloud_project()}/locations/{config.google_cloud_location()}"
    client = _client()
    inspect = _inspect_config()
    deid = _deidentify_config()
    masked: list[str] = []
    total = 0
    for chunk in _chunks(text):
        resp = await client.deidentify_content(
            request={
                "parent": parent,
                "deidentify_config": deid,
                "inspect_config": inspect,
                "item": {"value": chunk},
            }
        )
        masked.append(resp.item.value)
        overview = resp.overview
        if overview and overview.transformation_summaries:
            total += sum(r.count for s in overview.transformation_summaries for r in s.results)
    return "".join(masked), total
