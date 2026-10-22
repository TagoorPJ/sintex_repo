"""
Data repository layer for Sintex Water Solutions.
Loads and caches structured catalog and domain knowledge from JSON files.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_DATA_DIR = Path(__file__).resolve().parent / "data"

class SintexCatalogRepository:
    _instance: Optional[SintexCatalogRepository] = None

    def __init__(self) -> None:
        self._tanks_data: List[Dict[str, Any]] = []
        self._domain_knowledge: Dict[str, Any] = {}
        self._tanks_by_id: Dict[str, Dict[str, Any]] = {}
        self._alias_map: Dict[str, str] = {}
        self._load_data()
        self._build_alias_index()

    @classmethod
    def get_instance(cls) -> SintexCatalogRepository:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_data(self) -> None:
        tanks_file = _DATA_DIR / "tanks_catalog.json"
        knowledge_file = _DATA_DIR / "domain_knowledge.json"

        if tanks_file.exists():
            with open(tanks_file, "r", encoding="utf-8") as f:
                content = json.load(f)
                self._tanks_data = content.get("tanks", [])
                for tank in self._tanks_data:
                    self._tanks_by_id[tank["id"]] = tank

        if knowledge_file.exists():
            with open(knowledge_file, "r", encoding="utf-8") as f:
                self._domain_knowledge = json.load(f)

    def _build_alias_index(self) -> None:
        aliases = {
            "eterno": "sintex_eterno",
            "sintex eterno": "sintex_eterno",
            "pure": "sintex_pure",
            "sintex pure": "sintex_pure",
            "pure+": "sintex_pure_plus",
            "pure plus": "sintex_pure_plus",
            "sintex pure+": "sintex_pure_plus",
            "sintex pure plus": "sintex_pure_plus",
            "tatva": "sintex_tatva",
            "sintex tatva": "sintex_tatva",
            "trupuf": "sintex_trupuf",
            "tru puf": "sintex_trupuf",
            "puf": "sintex_trupuf",
            "sintex trupuf": "sintex_trupuf",
            "sintex puf": "sintex_trupuf",
            "neo": "sintex_neo",
            "sintex neo": "sintex_neo",
            "smart": "sintex_smart",
            "sintex smart": "sintex_smart",
            "reno": "sintex_reno",
            "sintex reno": "sintex_reno",
            "titus": "sintex_titus",
            "sintex titus": "sintex_titus",
            "hero": "sintex_hero",
            "sintex hero": "sintex_hero",
            "ace": "sintex_ace",
            "sintex ace": "sintex_ace",
            "side hatch": "sintex_ace",
            "classic": "sintex_classic",
            "sintex classic": "sintex_classic",
            "isi": "sintex_isi",
            "sintex isi": "sintex_isi",
            "loft": "sintex_loft",
            "sintex loft": "sintex_loft",
            "sump": "sintex_underground_sump",
            "underground sump": "sintex_underground_sump",
            "sintex sump": "sintex_underground_sump",
            "frp": "sintex_underground_frp",
            "underground frp": "sintex_underground_frp",
            "community panel": "sintex_pure_community_panel_tank",
            "panel tank": "sintex_pure_community_panel_tank",
            "community": "sintex_pure_community_panel_tank",
            "septic": "sintex_advanced_septic_tank",
            "septic tank": "sintex_advanced_septic_tank",
            "ast": "sintex_advanced_septic_tank",
            "pwts": "sintex_advanced_septic_tank",
            "stp": "sintex_packaged_stp",
            "sewage treatment": "sintex_packaged_stp",
        }
        for k, v in aliases.items():
            self._alias_map[k.lower().strip()] = v

    def resolve_tank_id(self, name_or_alias: str) -> Optional[str]:
        if not name_or_alias:
            return None
        cleaned = name_or_alias.lower().strip()
        if cleaned in self._tanks_by_id:
            return cleaned
        if cleaned in self._alias_map:
            return self._alias_map[cleaned]
        for tank in self._tanks_data:
            if cleaned in tank["name"].lower() or tank["name"].lower() in cleaned:
                return tank["id"]
        return None

    def get_tank_by_id(self, tank_id: str) -> Optional[Dict[str, Any]]:
        return self._tanks_by_id.get(tank_id)

    def get_all_tanks(self) -> List[Dict[str, Any]]:
        return self._tanks_data

    def get_domain_knowledge(self) -> Dict[str, Any]:
        return self._domain_knowledge
