"""Decisive diagnostic v2: print module path + _fetch_1688_product source + return.

Also monkeypatches the function call to trace every return path.
"""
import inspect
import os
import sys
import traceback

print("DIAG LOGIN_COOKIE len:", len(os.environ.get("LOGIN_COOKIE", "")))

import app.services.product_pipeline_service as m  # noqa: E402

print("DIAG module file:", m.__file__)
print("DIAG has _fetch_1688_product:", hasattr(m, "_fetch_1688_product"))

try:
    src = inspect.getsource(m._fetch_1688_product)
    print("DIAG source length:", len(src))
    # print only return statements to see all exit paths
    for i, line in enumerate(src.splitlines(), 1):
        if "return" in line or "raise" in line or "except" in line:
            print("DIAG src l%d: %s" % (i, line.strip()[:110]))
except Exception as e:
    print("DIAG getsource failed:", e)

print("DIAG --- calling _fetch_1688_product ---")
try:
    r = m._fetch_1688_product("964465929482")
    print("DIAG return type:", type(r).__name__)
    print("DIAG raw repr:", repr(r)[:400])
except Exception:
    traceback.print_exc()
