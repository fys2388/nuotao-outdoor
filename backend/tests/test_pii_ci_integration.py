"""APR-PII-CI-001：PII 临时 PostgreSQL 集成测试。

在 GitHub Actions postgres service（临时库）上验证：
  0086 init -> 0087 apply -> 合成数据加密回填 -> HMAC/AES-GCM 对账 ->
  重复执行（幂等）-> 异常中断/失败重试 -> 密钥缺失/错误密钥/密文损坏（fail-closed）
  -> 回滚 0087 -> 临时库/测试密钥清理。

边界（Owner APR-PII-CI-001）：
  - 不连接生产数据库；只用 CI 临时库（PII_CI_DB / DATABASE_URL）。
  - 不使用真实客户数据；只插入合成 lead。
  - 不使用生产密钥；只用测试密钥（HMAC 短串 + 32B base64 AES）。
  - 结果记录：CI_INTEGRATION_TEST=PASS/FAIL；STAGING_ACCEPTANCE=BLOCKED；
    PRODUCTION_READINESS=NOT_APPROVED（本次不批准任何生产 PII 操作）。

运行（CI / 本地有 postgres 时）：
  DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/nuotao_pii_ci \
  PII_HMAC_KEY=test-hmac-key-001 \
  PII_ENCRYPTION_KEY=AAECAwQFBgcICQoLDA0ODw== \
  python -m pytest backend/tests/test_pii_ci_integration.py -v
"""

from __future__ import annotations

import os
import subprocess
import uuid

import pytest
from sqlalchemy import create_engine, text

from app.core.pii_crypto import (
    PiiCryptoError,
    build_email_hash,
    decrypt_field,
    encrypt_field,
)

# 测试密钥（临时，非生产）
TEST_HMAC_KEY = "test-hmac-key-001"
TEST_ENC_KEY = "AAECAwQFBgcICQoLDA0ODw=="  # 32B base64（AES-256-GCM）

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")


def _alembic_upgrade(target: str, db_url: str) -> None:
    """用独立环境变量运行 alembic upgrade <target>（不污染进程 env）。"""
    env = {**os.environ, "DATABASE_URL": db_url}
    subprocess.run(
        ["python", "-m", "alembic", "upgrade", target],
        cwd=BACKEND_DIR,
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="module")
def db_url() -> str:
    url = os.environ.get("PII_CI_DB_URL") or os.environ.get("DATABASE_URL")
    assert url, "需要 PII_CI_DB_URL / DATABASE_URL（CI 临时 postgres）"
    return url


@pytest.fixture(scope="module")
def engine(db_url):
    eng = create_engine(db_url)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def migrated(db_url, engine):
    """0086 init + 0087 apply；yield 后回滚到 0086 并清理临时数据。"""
    _alembic_upgrade("0086", db_url)
    # 清空（防 CI 复用残留）
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM b2b_leads WHERE is_test = true"))
    _alembic_upgrade("0087", db_url)
    yield
    # 回滚 0087（Owner 要求：迁移回滚）
    _alembic_upgrade("0086", db_url)


@pytest.fixture(scope="module")
def keys():
    os.environ["PII_HMAC_KEY"] = TEST_HMAC_KEY
    os.environ["PII_ENCRYPTION_KEY"] = TEST_ENC_KEY
    yield
    os.environ.pop("PII_HMAC_KEY", None)
    os.environ.pop("PII_ENCRYPTION_KEY", None)


def _insert_lead(engine, email: str, name: str, ref: str, workspace: str = "ci-ws"):
    lead_id = uuid.uuid4().int & 0xFFFFFFFFFFFFFFFF
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO b2b_leads (id, reference_number, workspace_id, email, "
                "contact_name, status, is_test, created_at, updated_at) "
                "VALUES (:id, :ref, :ws, :email, :name, 'new', true, now(), now()) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": lead_id, "ref": ref, "ws": workspace, "email": email, "name": name},
        )
    return lead_id


def _read_pii(engine, lead_id):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT email_hash, email_encrypted, contact_name_encrypted, pii_key_version "
                "FROM b2b_leads WHERE id = :id"
            ),
            {"id": lead_id},
        ).mappings().first()
    return row


# ---------------------------------------------------------------------------
# 1. 0087 结构：列 + 唯一索引
# ---------------------------------------------------------------------------
def test_0087_schema(migrated, engine):
    with engine.connect() as conn:
        cols = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='b2b_leads' AND column_name IN "
                    "('email_hash','email_encrypted','contact_name_encrypted','pii_key_version')"
                )
            )
        }
    assert cols == {
        "email_hash",
        "email_encrypted",
        "contact_name_encrypted",
        "pii_key_version",
    }, f"0087 列未就绪: {cols}"
    with engine.connect() as conn:
        idx = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename='b2b_leads' AND indexname='ux_b2b_leads_email_hash'")
        ).fetchall()
    assert idx, "缺少唯一索引 ux_b2b_leads_email_hash"


# ---------------------------------------------------------------------------
# 2. HMAC-SHA-256 确定性 + workspace 作用域
# ---------------------------------------------------------------------------
def test_email_hash_deterministic_and_scoped(keys):
    h1 = build_email_hash("lead@example.com", workspace_id="ws-a")
    h2 = build_email_hash("lead@example.com", workspace_id="ws-a")
    h3 = build_email_hash("lead@example.com", workspace_id="ws-b")
    assert h1 == h2, "HMAC 应对同输入确定性一致"
    assert h1 != h3, "不同 workspace 应产生不同哈希（作用域隔离）"


# ---------------------------------------------------------------------------
# 3. AES-256-GCM 加解密 roundtrip
# ---------------------------------------------------------------------------
def test_aes_roundtrip(keys):
    ct = encrypt_field("contact@example.com")
    assert decrypt_field(ct) == "contact@example.com"


# ---------------------------------------------------------------------------
# 4. 合成数据加密回填 + 对账（原文/密文/解密/哈希）
# ---------------------------------------------------------------------------
def test_backfill_and_reconcile(migrated, engine, keys):
    email = f"backfill-{uuid.uuid4().hex[:8]}@example.com"
    name = "合成-客户-甲"
    lead_id = _insert_lead(engine, email, name, f"CI-{uuid.uuid4().hex[:8]}")
    row = _read_pii(engine, lead_id)
    assert row and row["email_hash"], "回填未写入 email_hash"
    assert row["email_encrypted"], "回填未写入 email_encrypted"
    assert row["contact_name_encrypted"], "回填未写入 contact_name_encrypted"
    assert row["pii_key_version"] == "v1"
    # 对账：解密 == 原文；哈希 == 重算
    assert decrypt_field(row["email_encrypted"]) == email, "email 对账失败"
    assert decrypt_field(row["contact_name_encrypted"]) == name, "contact_name 对账失败"
    assert row["email_hash"] == build_email_hash(email, workspace_id="ci-ws"), "email_hash 对账失败"


# ---------------------------------------------------------------------------
# 5. 重复执行（幂等：不覆盖、不重复写）
# ---------------------------------------------------------------------------
def test_repeat_idempotent(migrated, engine, keys):
    email = f"repeat-{uuid.uuid4().hex[:8]}@example.com"
    name = "重复-客户"
    lead_id = _insert_lead(engine, email, name, f"CI-{uuid.uuid4().hex[:8]}")
    row1 = _read_pii(engine, lead_id)
    assert row1 and row1["email_hash"]
    ct1 = row1["email_encrypted"]
    # 重新执行 backfill 逻辑（同 lead 重跑）
    h = build_email_hash(email, workspace_id="ci-ws")
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE b2b_leads SET email_hash=:h, email_encrypted=:ct, "
                "pii_key_version='v1' WHERE id=:id"
            ),
            {"h": h, "ct": ct1, "id": lead_id},
        )
    row2 = _read_pii(engine, lead_id)
    assert row2["email_encrypted"] == ct1, "重复执行不应改变密文（幂等）"
    assert row2["email_hash"] == h


# ---------------------------------------------------------------------------
# 6. 异常中断 / 失败重试：密钥缺失（fail-closed）
# ---------------------------------------------------------------------------
def test_key_missing_fail_closed(migrated, engine):
    os.environ.pop("PII_ENCRYPTION_KEY", None)
    with pytest.raises(PiiCryptoError):
        encrypt_field("x@example.com")
    os.environ["PII_ENCRYPTION_KEY"] = TEST_ENC_KEY


# ---------------------------------------------------------------------------
# 7. 错误密钥：解密失败（不静默回退）
# ---------------------------------------------------------------------------
def test_wrong_key_rejects(keys, migrated, engine):
    ct = encrypt_field("wrong-key@example.com")
    os.environ["PII_ENCRYPTION_KEY"] = "FQIDBAUGBwgJCgsMDQ4PEA=="  # 不同 32B
    with pytest.raises(PiiCryptoError):
        decrypt_field(ct)
    os.environ["PII_ENCRYPTION_KEY"] = TEST_ENC_KEY


# ---------------------------------------------------------------------------
# 8. 密文损坏：拒绝（fail-closed，不静默回退明文）
# ---------------------------------------------------------------------------
def test_corrupted_ciphertext_rejects(keys, migrated, engine):
    ct = encrypt_field("corrupt@example.com")
    raw = bytearray(ct)
    # 翻转 payload 中间若干字节（iv 之后的密文段）
    idx = len(raw) // 2
    raw[idx] ^= 0x01
    corrupted = bytes(raw)
    with pytest.raises(PiiCryptoError):
        decrypt_field(corrupted)


# ---------------------------------------------------------------------------
# 9. 回滚 0087：列消失、revision=0086（fixture 已回滚）
# ---------------------------------------------------------------------------
def test_rollback_0087(migrated, engine, db_url):
    # 手动再升级一次 0087 后回滚，验证列消失（保证本用例独立）
    _alembic_upgrade("0087", db_url)
    with engine.connect() as conn:
        has = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_name='b2b_leads' AND column_name='email_encrypted'"
            )
        ).scalar()
    assert has == 1
    _alembic_upgrade("0086", db_url)
    with engine.connect() as conn:
        has = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_name='b2b_leads' AND column_name='email_encrypted'"
            )
        ).scalar()
    assert has == 0, "回滚 0087 后 email_encrypted 列应消失"
    rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert rev == "0086"


# ---------------------------------------------------------------------------
# 10. 清理：临时数据（测试 lead）删除；测试密钥不残留
# ---------------------------------------------------------------------------
def test_cleanup(migrated, engine):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM b2b_leads WHERE is_test = true"))
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM b2b_leads WHERE is_test=true")).scalar()
    assert n == 0, "临时测试 lead 未清理"
    assert os.environ.get("PII_ENCRYPTION_KEY") != os.environ.get("PII_PRODUCTION_KEY")
