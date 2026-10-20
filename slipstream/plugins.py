"""Reflex compiler plugins used by the Slipstream frontend."""

import reflex as rx
from typing_extensions import Unpack

_VITE_MAIN_FIELDS = '    mainFields: ["browser", "module", "jsnext"],'
_VITE_REACT_DEDUPE = '    dedupe: ["react", "react-dom"],'


def _dedupe_react_vite_config(content: str) -> str:
    """Make the Reflex renderer and local JSX assets resolve one React copy."""
    if _VITE_REACT_DEDUPE in content:
        return content
    if _VITE_MAIN_FIELDS not in content:
        raise RuntimeError(
            "Could not add React deduplication to the generated Vite config"
        )
    return content.replace(
        _VITE_MAIN_FIELDS,
        f"{_VITE_REACT_DEDUPE}\n{_VITE_MAIN_FIELDS}",
        1,
    )


class ReactDedupePlugin(rx.plugins.Plugin):
    """Deduplicate React for Reflex's renderer and wrapped local components."""

    def pre_compile(
        self, **context: Unpack[rx.plugins.PreCompileContext]
    ) -> None:
        """Add Vite's React dedupe option to the generated frontend config."""
        context["add_modify_task"]("vite.config.js", _dedupe_react_vite_config)
