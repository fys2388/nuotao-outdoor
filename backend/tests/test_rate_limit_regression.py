"""M4 V2.7.1 rate_limit.py ``_read_file(*args, **kwargs)`` 鍏煎鍥炲綊娴嬭瘯.

鑳屾櫙:starlette 1.6.0 鐨?``Config.__init__`` 鏀逛负璋冪敤 ``self._read_file(env_file, encoding)``
(澶氫紶 encoding),鏃?monkeypatch 绛惧悕 ``_fixed_read_file(self, env_file)`` 鎶?TypeError,
瀵艰嚧鍏变韩 ``tests/conftest.py`` 椤跺眰瀵煎叆 ``app.api.v1.endpoints.auth`` 澶辫触銆?淇:鏀逛负 ``_fixed_read_file(self, *args, **kwargs)``,榛樿琛?``encoding='utf-8'``
骞?*濮旀墭鍥炲師濮?``_read_file``**(淇濇寔鍏?``dict`` 杩斿洖濂戠害),閬垮厤 Windows GBK 鎶ラ敊銆?
鏈祴璇?*涓嶅彧浠?conftest 鍙姞杞戒负楠屾敹**,鐩存帴楠岃瘉:
- patch 宸插畨瑁呬笖淇濆瓨鍘熷閫昏緫;
- 鏈夋晥 env 鏂囦欢缁?patched ``_read_file`` 杩斿洖 ``dict`` 涓旈敭鍊兼纭?
- 鏂版棫涓ょ璋冪敤绾﹀畾(浠?env_file / env_file+encoding)鍧囦笉鎶?TypeError;
- 鍘熷 ``Config`` 鑳界粡 patch 姝ｅ父浠?env 鏂囦欢璇诲嚭閿€?绔埌绔?;
- 鍘熸湁闄愭祦甯搁噺涓嶅彉銆?"""

from __future__ import annotations

import starlette.config
from starlette.config import Config

from app.core import rate_limit
from app.core.rate_limit import (
    RATE_LIMIT_ADMIN,
    RATE_LIMIT_AUTH,
    RATE_LIMIT_DEFAULT,
    _fixed_read_file,
    limiter,
    rate_limit_exceeded_handler,
)


def test_patch_installed_and_wraps_original() -> None:
    """monkeypatch 宸插畨瑁?涓斾繚瀛樹簡鍘熷 ``_read_file`` 閫昏緫."""
    assert starlette.config.Config._read_file is _fixed_read_file
    assert callable(rate_limit._original_read_file)


def test_read_file_valid_env_file(tmp_path) -> None:
    """鏈夋晥 env 鏂囦欢:杩斿洖 dict 涓旇В鏋愬嚭閿€?濮旀墭鍘熷 _read_file)."""
    env = tmp_path / ".env"
    env.write_text("FOO=bar\nBAZ=qux\n", encoding="utf-8")
    result = _fixed_read_file(object(), env, "utf-8")
    assert isinstance(result, dict)
    assert result["FOO"] == "bar"
    assert result["BAZ"] == "qux"


def test_read_file_accepts_legacy_single_arg(tmp_path) -> None:
    """鏃ц皟鐢ㄧ害瀹?浠?env_file,鏃?encoding):榛樿琛?utf-8,涓嶆姤 TypeError."""
    env = tmp_path / ".env"
    env.write_text("K=v\n", encoding="utf-8")
    result = _fixed_read_file(object(), env)
    assert result == {"K": "v"}


def test_read_file_accepts_kwargs(tmp_path) -> None:
    """kwargs 璋冪敤(env_file=/encoding=):鍏煎涓旇繑鍥?dict."""
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")
    result = _fixed_read_file(object(), env, encoding="utf-8")
    assert result == {"A": "1"}


def test_config_end_to_end_loads_env_file(tmp_path) -> None:
    """绔埌绔?Config(env_file=...) 缁?patched _read_file 姝ｅ父璇诲嚭閿€?"""
    env = tmp_path / ".env"
    env.write_text("APP_SETTING=hello\n", encoding="utf-8")
    cfg = Config(env_file=env)
    assert cfg("APP_SETTING") == "hello"


def test_rate_limit_constants_unchanged() -> None:
    """鍘熸湁闄愭祦甯搁噺涓嶅彉(鍥炲綊淇濇姢)."""
    assert RATE_LIMIT_DEFAULT == "100/minute"
    assert RATE_LIMIT_AUTH == "10/minute"
    assert RATE_LIMIT_ADMIN == "50/minute"


def test_limiter_instance_present() -> None:
    """limiter 瀹炰緥瀛樺湪涓旈粯璁ら檺娴佸凡閰嶇疆(1 鏉?default limit)."""
    assert limiter is not None
    assert len(limiter._default_limits) >= 1
    assert limiter.enabled is True


def test_rate_limit_exceeded_handler_shape() -> None:
    """闄愭祦瓒呴 handler 杩斿洖绋冲畾 JSON 缁撴瀯(涓嶆毚闇插唴閮ㄥ爢鏍?."""

    class _RateLimitError(Exception):
        limit = "10/minute"
        time_to_expiration = 42

    resp = rate_limit_exceeded_handler(object(), _RateLimitError())
    assert resp["error"] == "rate_limit_exceeded"
    assert "10/minute" in resp["message"]
    assert resp["retry_after"] == 42


def test_original_read_file_still_callable(tmp_path) -> None:
    """纭鍘熷 ``_read_file`` 閫昏緫浠嶅彲璋冪敤(patch 鏈牬鍧忓簳灞傝鍙栬兘鍔?."""
    env = tmp_path / ".env"
    env.write_text("X=1\n", encoding="utf-8")
    result = rate_limit._original_read_file(object(), env, "utf-8")
    assert isinstance(result, dict)
    assert result["X"] == "1"
