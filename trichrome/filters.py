"""Persisted registry of filename "filter" definitions (display name + the
tokens that identify them in a filename) used by the Automatic batch-import
matcher. Ships with 5 built-in filters (Red/Green/Blue/Yellow/Infrared);
users can add their own (e.g. "Cyan") and edit any filter's name/tokens, plus
pick a manual filter->channel mapping for the "Custom" Advanced Options mode.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings

from . import i18n

ORG_NAME = "TrichromeMaker"
APP_NAME = "TrichromeMaker"

BUILTIN_IDS = ("R", "G", "B", "Y", "IR")
CHANNELS = ("R", "G", "B")

_BUILTIN_DEFAULTS = {
    "R": {"name_key": "channel_r", "tokens": ["r", "red", "rouge"]},
    "G": {"name_key": "channel_g", "tokens": ["g", "v", "green", "vert"]},
    "B": {"name_key": "channel_b", "tokens": ["b", "blue", "bleu"]},
    "Y": {"name_key": "filter_yellow", "tokens": ["y", "j", "yellow", "jaune"]},
    "IR": {"name_key": "filter_infrared", "tokens": ["ir", "infrared", "infrarouge"]},
}


@dataclass
class FilterDef:
    id: str
    name: str
    tokens: list[str]
    builtin: bool


class FilterRegistry:
    def __init__(self):
        self._custom: dict[str, dict] = {}
        self._builtin_overrides: dict[str, dict] = {}
        self._next_custom_num = 1
        self._load()

    # ------------------------------------------------------------------
    def list_filters(self) -> list[FilterDef]:
        result = []
        for fid in BUILTIN_IDS:
            defaults = _BUILTIN_DEFAULTS[fid]
            override = self._builtin_overrides.get(fid, {})
            name = override.get("name") or i18n.tr(defaults["name_key"])
            tokens = override.get("tokens") or list(defaults["tokens"])
            result.append(FilterDef(id=fid, name=name, tokens=list(tokens), builtin=True))
        for fid, data in self._custom.items():
            result.append(FilterDef(id=fid, name=data["name"], tokens=list(data["tokens"]), builtin=False))
        return result

    def get(self, filter_id: str) -> FilterDef | None:
        for f in self.list_filters():
            if f.id == filter_id:
                return f
        return None

    def add_filter(self, name: str, tokens: list[str]) -> FilterDef:
        fid = f"CUSTOM_{self._next_custom_num}"
        self._next_custom_num += 1
        self._custom[fid] = {"name": name, "tokens": tokens}
        self._save()
        return FilterDef(id=fid, name=name, tokens=tokens, builtin=False)

    def update_filter(self, filter_id: str, name: str | None = None, tokens: list[str] | None = None) -> None:
        if filter_id in BUILTIN_IDS:
            override = self._builtin_overrides.setdefault(filter_id, {})
            if name is not None:
                override["name"] = name
            if tokens is not None:
                override["tokens"] = tokens
        elif filter_id in self._custom:
            if name is not None:
                self._custom[filter_id]["name"] = name
            if tokens is not None:
                self._custom[filter_id]["tokens"] = tokens
        else:
            return
        self._save()

    def remove_filter(self, filter_id: str) -> None:
        if filter_id in self._custom:
            del self._custom[filter_id]
            self._save()

    def tokens_map(self) -> dict[str, list[str]]:
        return {f.id: [t.lower().strip() for t in f.tokens if t.strip()] for f in self.list_filters()}

    # ------------------------------------------------------------------
    # Custom-mode manual channel mapping (which filter feeds which digital
    # R/G/B channel when Advanced Options is set to "Custom").
    # ------------------------------------------------------------------
    def get_custom_mapping(self) -> dict[str, str]:
        settings = QSettings(ORG_NAME, APP_NAME)
        mapping = {}
        for channel in CHANNELS:
            value = settings.value(f"custom_mode_filter_{channel}", "", type=str)
            if value:
                mapping[channel] = value
        return mapping

    def set_custom_mapping(self, channel: str, filter_id: str | None) -> None:
        settings = QSettings(ORG_NAME, APP_NAME)
        settings.setValue(f"custom_mode_filter_{channel}", filter_id or "")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self) -> None:
        settings = QSettings(ORG_NAME, APP_NAME)
        count = settings.beginReadArray("custom_filters")
        for i in range(count):
            settings.setArrayIndex(i)
            fid = settings.value("id", "", type=str)
            name = settings.value("name", "", type=str)
            tokens_str = settings.value("tokens", "", type=str)
            tokens = [t for t in tokens_str.split(",") if t]
            if fid and name:
                self._custom[fid] = {"name": name, "tokens": tokens}
                try:
                    num = int(fid.replace("CUSTOM_", ""))
                    self._next_custom_num = max(self._next_custom_num, num + 1)
                except ValueError:
                    pass
        settings.endArray()

        count = settings.beginReadArray("builtin_filter_overrides")
        for i in range(count):
            settings.setArrayIndex(i)
            fid = settings.value("id", "", type=str)
            name = settings.value("name", "", type=str)
            tokens_str = settings.value("tokens", "", type=str)
            if fid in BUILTIN_IDS:
                override = {}
                if name:
                    override["name"] = name
                if tokens_str:
                    override["tokens"] = [t for t in tokens_str.split(",") if t]
                if override:
                    self._builtin_overrides[fid] = override
        settings.endArray()

    def _save(self) -> None:
        settings = QSettings(ORG_NAME, APP_NAME)
        settings.remove("custom_filters")
        settings.beginWriteArray("custom_filters", len(self._custom))
        for i, (fid, data) in enumerate(self._custom.items()):
            settings.setArrayIndex(i)
            settings.setValue("id", fid)
            settings.setValue("name", data["name"])
            settings.setValue("tokens", ",".join(data["tokens"]))
        settings.endArray()

        settings.remove("builtin_filter_overrides")
        settings.beginWriteArray("builtin_filter_overrides", len(self._builtin_overrides))
        for i, (fid, override) in enumerate(self._builtin_overrides.items()):
            settings.setArrayIndex(i)
            settings.setValue("id", fid)
            settings.setValue("name", override.get("name", ""))
            settings.setValue("tokens", ",".join(override.get("tokens", [])))
        settings.endArray()


registry = FilterRegistry()
