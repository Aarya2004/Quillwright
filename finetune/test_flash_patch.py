"""Unit tests for the flash_attn import-check patch (pure logic, GPU-free).

MiniCPM-V-2_6's remote modeling file has `import flash_attn` near the top. transformers'
check_imports() scans the file's imports and ImportErrors on any missing one — it doesn't
understand that the flash_attn path is only taken when you SELECT flash attention. We load
with attn_implementation='sdpa', so flash_attn is never used at runtime; the patch strips
it from the imports list check_imports insists on.

The PUBLISHED workaround only strips flash_attn `if not torch.cuda.is_available()` — which
no-ops on a GPU (our case), so the error would persist. Our version strips it
UNCONDITIONALLY, which is correct precisely because we force SDPA. These tests pin that
behavior without needing torch/CUDA.
"""

from flash_patch import strip_flash_attn


def test_strips_flash_attn_when_present():
    assert strip_flash_attn(["torch", "flash_attn", "PIL"]) == ["torch", "PIL"]


def test_noop_when_flash_attn_absent():
    assert strip_flash_attn(["torch", "PIL"]) == ["torch", "PIL"]


def test_strips_unconditionally_order_preserved():
    # The published patch guards on `not torch.cuda.is_available()`; ours does not.
    # Order of the remaining imports must be preserved (check_imports compares names only,
    # but a stable transform is easier to reason about).
    assert strip_flash_attn(["a", "flash_attn", "b", "c"]) == ["a", "b", "c"]


def test_empty_list():
    assert strip_flash_attn([]) == []
