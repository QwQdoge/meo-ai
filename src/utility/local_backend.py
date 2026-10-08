"""UI-free metadata for installed local inference backends."""
import builtins
import gettext
import os
import re
from pathlib import Path

_ = getattr(builtins, "_", gettext.gettext)

def _backend_from_cmake_cache(handler):
    source_dir = {
        "llamacpp": "llama_cpp_path",
        "llamacppembedding": "llama_cpp_path",
        "stablediffusioncpp": "sd_cpp_path",
        "whispercpp": "whisper_cpp_path",
    }.get(getattr(handler, "key", ""))
    if not source_dir or not getattr(handler, source_dir, None):
        return None
    cache_path = Path(getattr(handler, source_dir)) / "build" / "CMakeCache.txt"
    try:
        cache = cache_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    options = {
        "cuda": ("GGML_CUDA", "SD_CUDA"),
        "rocm": ("GGML_HIPBLAS", "SD_HIPBLAS"),
        "vulkan": ("GGML_VULKAN", "SD_VULKAN"),
        "openvino": ("GGML_OPENVINO",),
        "sycl-fp16": ("GGML_SYCL_F16",),
        "sycl-fp32": ("GGML_SYCL",),
    }
    for backend, flags in options.items():
        if any(re.search(rf"^{flag}:BOOL=ON$", cache, re.MULTILINE) for flag in flags):
            return backend
    if re.search(r"^(?:GGML_BLAS|GGML_OPENBLAS):BOOL=ON$", cache, re.MULTILINE):
        return "cpu_openblas"
    return "cpu"


def get_local_backend(handler):
    """Return the installed built-in backend, or None when no binary exists."""
    key = getattr(handler, "key", "")
    if key not in ("llamacpp", "llamacppembedding", "stablediffusioncpp", "whispercpp"):
        return None

    def setting(name, default=False):
        try:
            return handler.get_setting(name, False, default)
        except Exception:  # noqa: BLE001 - handler boundary
            return default

    if key == "stablediffusioncpp":
        binary_installed = any(
            path and os.path.isfile(path) and os.access(path, os.X_OK)
            for path in (
                getattr(handler, "sd_binary_path", None),
                getattr(handler, "sd_server_binary_path", None),
            )
        )
    else:
        installed = getattr(handler, "is_gpu_installed", None)
        try:
            binary_installed = callable(installed) and installed()
        except Exception:  # noqa: BLE001 - handler boundary
            binary_installed = False
    if not binary_installed:
        return None

    backend = setting("prebuilt_backend", None) if key in ("llamacpp", "llamacppembedding") else setting("installed_backend", None)
    if backend is None and key in ("llamacpp", "llamacppembedding") and setting("prebuilt", False):
        backend = "cuda" if setting("prebuilt_cuda") else "cpu"
    if backend is None:
        backend = _backend_from_cmake_cache(handler)
    return backend if backend in (
        "cpu", "cpu_openblas", "cuda", "rocm", "vulkan", "openvino", "sycl-fp32", "sycl-fp16"
    ) else "unknown"


def get_local_backend_label(handler):
    backend = get_local_backend(handler)
    labels = {
        None: _("No built-in binary installed"),
        "cpu": _("CPU"),
        "cpu_openblas": _("CPU (OpenBLAS)"),
        "cuda": _("NVIDIA CUDA"),
        "rocm": _("AMD ROCm"),
        "vulkan": _("Vulkan"),
        "openvino": _("Intel OpenVINO"),
        "sycl-fp32": _("Intel SYCL (FP32)"),
        "sycl-fp16": _("Intel SYCL (FP16)"),
        "unknown": _("Unknown backend for existing installation; reinstall to identify"),
    }
    return labels[backend]
