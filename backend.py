import os
import shutil
from typing import Set, Tuple, List

DEFAULT_CHUNK_SIZE = 64 * 1024 * 1024  # 64 MB


def _normalize_rel(path: str) -> str:
    """Normalize relative path separators to forward slashes for consistent set comparisons."""
    return path.replace("\\", "/")


def list_files_recursive(path: str) -> Set[str]:
    """Return a set of normalized relative file paths for all files in 'path' (recursive)."""
    files: Set[str] = set()
    for root, _, filenames in os.walk(path):
        for f in filenames:
            rel_path = os.path.relpath(os.path.join(root, f), path)
            files.add(_normalize_rel(rel_path))
    return files


def compare(origin: str, dest: str) -> Set[str]:
    """
    Return set of relative file paths present in origin but missing in dest.
    Comparison is by normalized relative path (structure-preserving).
    """
    origin_files = list_files_recursive(origin)
    dest_files = list_files_recursive(dest)
    return origin_files - dest_files


def ensure_parent_dir(path: str) -> None:
    """Ensure parent directory exists for 'path'."""
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def copy_file(src: str, dst: str, chunked: bool = False, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
    """
    Copy a file from src to dst.
    - If chunked=True, use manual chunked copy (good for very large files).
    - Otherwise, use shutil.copy2 (fast path and preserves metadata).
    """
    ensure_parent_dir(dst)

    if not chunked:
        shutil.copy2(src, dst)
        return

    # Chunked copy (robust for multi-GB files; preserves basic content, not extended metadata)
    with open(src, "rb") as r, open(dst, "wb") as w:
        while True:
            buf = r.read(chunk_size)
            if not buf:
                break
            w.write(buf)

    # Preserve timestamps if possible
    try:
        st = os.stat(src)
        os.utime(dst, (st.st_atime, st.st_mtime))
    except Exception:
        pass


def copy_missing_files(missing_files: Set[str], origin: str, dest: str, chunked: bool = False) -> Tuple[int, List[str]]:
    """
    Copy all missing files from origin to dest, preserving folder structure.
    Returns (success_count, errors_list).
    """
    success = 0
    errors: List[str] = []

    for rel_path in sorted(missing_files):
        rel_norm = _normalize_rel(rel_path)
        src = os.path.join(origin, rel_norm)
        dst = os.path.join(dest, rel_norm)
        try:
            copy_file(src, dst, chunked=chunked)
            success += 1
        except Exception as e:
            errors.append(f"{rel_norm} -> ERROR: {e}")

    return success, errors
