"""Work around MiniCPM-V-2_6's hard flash_attn import requirement (GPU-free helper).

The model's remote modeling file contains `import flash_attn`. transformers'
`check_imports()` statically scans that file and raises ImportError if flash_attn is not
installed — BEFORE the model is built, so `attn_implementation='sdpa'` never gets a chance
to route around it. flash_attn is just an optimized attention backend; SDPA (PyTorch's
built-in) is an equivalent, supported one (the model card itself loads with 'sdpa'). So we
strip flash_attn from the imports list `check_imports` insists on, then force SDPA at load.

`strip_flash_attn` is the pure list transform (unit-tested). `patched_get_imports` wraps it
for `unittest.mock.patch("transformers.dynamic_module_utils.get_imports", ...)`. Unlike the
published workaround, we strip UNCONDITIONALLY (no `torch.cuda.is_available()` guard) —
that guard no-ops on a GPU, which is exactly our environment, so the error would persist.
Safe because we always pass attn_implementation='sdpa' alongside this patch.

Usage (in a Modal remote function, where torch/transformers exist):

    from unittest.mock import patch
    from transformers.dynamic_module_utils import get_imports
    from flash_patch import make_patched_get_imports

    with patch("transformers.dynamic_module_utils.get_imports",
               make_patched_get_imports(get_imports)):
        model = AutoModel.from_pretrained(MODEL, trust_remote_code=True,
                                          attn_implementation="sdpa", torch_dtype=...)
"""


def strip_flash_attn(imports: list[str]) -> list[str]:
    """Return the imports list with 'flash_attn' removed (order preserved). Pure."""
    return [imp for imp in imports if imp != "flash_attn"]


def make_patched_get_imports(original_get_imports):
    """Wrap transformers' real get_imports so its result has flash_attn stripped.

    `original_get_imports` is `transformers.dynamic_module_utils.get_imports` — passed in
    rather than imported here so this module stays torch/transformers-free and unit-testable.
    """

    def _patched(filename):
        return strip_flash_attn(original_get_imports(filename))

    return _patched
