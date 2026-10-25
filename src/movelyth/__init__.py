"""Movelyth — 幕绎. From Idea to Final Cut."""

import os

# Apply only to this process and its children, before NumPy loads BLAS thread pools.
for _variable in ["OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"]:
    os.environ[_variable] = os.getenv("MOVELYTH_BLAS_THREADS", "1")

__version__ = "0.1.0"
