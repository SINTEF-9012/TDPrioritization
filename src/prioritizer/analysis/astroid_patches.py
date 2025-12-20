def patch_astroid_namespace_bug():
    """
    Work around a bug in astroid's namespace detection for certain environments.

    This patch is idempotent and safe to call at import time.
    """
    import astroid.interpreter._import.util as util  # type: ignore
    from pathlib import Path as _Path

    if hasattr(util, "is_namespace"):
        orig_any = util.is_namespace

        def safe_is_namespace(modname: str) -> bool:
            try:
                # Ensure it does not break if STD_AND_EXT_LIB_DIRS contains Path objects.
                for location in getattr(util, "STD_AND_EXT_LIB_DIRS", []):
                    if isinstance(location, _Path):
                        continue
                return orig_any(modname)
            except AttributeError:
                # If astroid internals change, fail closed but not catastrophically.
                return False

        util.is_namespace = safe_is_namespace  # type: ignore[assignment]