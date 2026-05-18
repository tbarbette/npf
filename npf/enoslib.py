# Backward-compatibility shim.
# The run() function is now available directly as npf.run().
# This module is kept so that existing code using
#   from npf import enoslib as npf; npf.run(...)
# continues to work unchanged.
from npf.api import run  # noqa: F401
