"""M4 V2.6 身份模型测试本地运行入口(复用交付测试,避开共享 conftest 崩溃).

通过 ``from tests.test_identity_model_v26 import *`` 复用正式交付的 17 项测试;
pytest 收集其中 ``test_*`` 函数,并使用本目录 ``conftest.py`` 提供的 db_session。
正式交付文件:``backend/tests/test_identity_model_v26.py``。
"""

from __future__ import annotations

from tests.test_identity_model_v26 import *  # noqa: F403
