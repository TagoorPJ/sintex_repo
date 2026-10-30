"""
Data repository layer for Sintex Water Solutions.
Loads and caches structured catalog and domain knowledge from JSON files.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from rapidfuzz import fuzz

_DATA_DIR = Path(__file__).resolve().parent / "data"

class SintexCatalogRepository:
    _instance: Optional[SintexCatalogRepository] = None

    def __init__(self) -> None:
        self._tanks_data: List[Dict[str, Any]] = []
        self._pipes_data: List[Dict[str, Any]] = []
        self._domain_knowledge: Dict[str, Any] = {}
        self._tanks_by_id: Dict[str, Dict[str, Any]] = {}
        self._pipes_by_id: Dict[str, Dict[str, Any]] = {}
        self._alias_map: Dict[str, str] = {}
        self._pipe_alias_map: Dict[str, str] = {}
        self._load_data()
        self._build_alias_index()

    @classmethod
    def get_instance(cls) -> SintexCatalogRepository:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_data(self) -> None:
        tanks_file = _DATA_DIR / "tanks_catalog.json"
        pipes_file = _DATA_DIR / "pipes_catalog.json"
        knowledge_file = _DATA_DIR / "domain_knowledge.json"

        if tanks_file.exists():
            with open(tanks_file, "r", encoding="utf-8") as f:
                content = json.load(f)
                self._tanks_data = content.get("tanks", [])
                for tank in self._tanks_data:
                    self._tanks_by_id[tank["id"]] = tank

        if pipes_file.exists():
            with open(pipes_file, "r", encoding="utf-8") as f:
                pcontent = json.load(f)
                self._pipes_data = pcontent.get("pipes", [])
                for pipe in self._pipes_data:
                    self._pipes_by_id[pipe["id"]] = pipe

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
            "plus": "sintex_pure_plus",
            "sintex plus": "sintex_pure_plus",
            "tatva": "sintex_tatva",
            "sintex tatva": "sintex_tatva",
            "trupuf": "sintex_trupuf",
            "tru puf": "sintex_trupuf",
            "puf": "sintex_trupuf",
            "sintex trupuf": "sintex_trupuf",
            "sintex puf": "sintex_trupuf",
            "turpuf": "sintex_trupuf",
            "sintex turpuf": "sintex_trupuf",
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
            "panel": "sintex_pure_community_panel_tank",
            "panel tank": "sintex_pure_community_panel_tank",
            "community panel": "sintex_pure_community_panel_tank",
            "community": "sintex_pure_community_panel_tank",
            "smc panel": "sintex_pure_community_panel_tank",
            "smc tank": "sintex_pure_community_panel_tank",
            "septic": "sintex_advanced_septic_tank",
            "septic tank": "sintex_advanced_septic_tank",
            "ast": "sintex_advanced_septic_tank",
            "pwts": "sintex_advanced_septic_tank",
            "stp": "sintex_packaged_stp",
            "sewage treatment": "sintex_packaged_stp",
        }
        for k, v in aliases.items():
            self._alias_map[k.lower().strip()] = v

        pipe_aliases = {
            "swrx": "sintex_swrx",
            "sintex swrx": "sintex_swrx",
            "swrx pro": "sintex_swrx",
            "sintex swrx pro": "sintex_swrx",
            "swr": "sintex_swrx",
            "swr pipe": "sintex_swrx",
            "swr pipes": "sintex_swrx",
            "swrx pipe": "sintex_swrx",
            "swrx pipes": "sintex_swrx",
            "anti rat": "sintex_swrx",
            "anti rat pipe": "sintex_swrx",
            "anti rodent": "sintex_swrx",
            "ratloc": "sintex_swrx",
            "rat loc": "sintex_swrx",
            "ratloc technology": "sintex_swrx",
            "nxt antirat": "sintex_swrx",
            "nxt anti rat": "sintex_swrx",
            "nxt antirate": "sintex_swrx",
            "3 layer pipe": "sintex_swrx",
            "type a": "sintex_swrx_type_a",
            "type a pipe": "sintex_swrx_type_a",
            "swrx type a": "sintex_swrx_type_a",
            "sintex swrx type a": "sintex_swrx_type_a",
            "type b": "sintex_swrx_type_b",
            "type b pipe": "sintex_swrx_type_b",
            "swrx type b": "sintex_swrx_type_b",
            "sintex swrx type b": "sintex_swrx_type_b",
            "ringfit": "sintex_swrx",
            "ring fit": "sintex_swrx",
            "selfit": "sintex_swrx",
            "solfit": "sintex_swrx",
            "sol fit": "sintex_swrx",
            "hotx": "sintex_hotx",
            "sintex hotx": "sintex_hotx",
            "coolx": "sintex_coolx",
            "sintex coolx": "sintex_coolx",
            "groundx": "sintex_groundx",
            "sintex groundx": "sintex_groundx",
            "agrix": "sintex_agrix",
            "sintex agrix": "sintex_agrix",
            "reclaimx": "sintex_reclaimx",
            "sintex reclaimx": "sintex_reclaimx",
            "surface drainage": "sintex_surface_drainage",
            "sintex surface drainage": "sintex_surface_drainage",
        }
        for k, v in pipe_aliases.items():
            self._pipe_alias_map[k.lower().strip()] = v

    def get_close_matches(self, name_or_alias: str, limit: int = 3) -> List[str]:
        if not name_or_alias:
            return []
        cleaned = name_or_alias.lower().strip()
        core_cleaned = cleaned.replace("sintex", "").replace("tank", "").strip()

        candidates = [t["name"] for t in self._tanks_data]
        scored = []
        for name in candidates:
            name_core = name.lower().replace("sintex", "").strip()
            score1 = fuzz.token_set_ratio(cleaned, name.lower())
            score2 = fuzz.ratio(core_cleaned, name_core) if core_cleaned else 0
            score3 = fuzz.partial_ratio(cleaned, name.lower())
            score = max(score1, score2, score3)
            scored.append((name, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [item[0] for item in scored[:limit] if item[1] >= 40]

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

        # Fuzzy match fallback: if confidence >= 80, resolve directly
        close = self.get_close_matches(name_or_alias, limit=1)
        if close:
            best_name = close[0]
            score = fuzz.token_set_ratio(cleaned, best_name.lower())
            if score >= 80:
                for tank in self._tanks_data:
                    if tank["name"] == best_name:
                        return tank["id"]

        return None

    def get_tank_by_id(self, tank_id: str) -> Optional[Dict[str, Any]]:
        return self._tanks_by_id.get(tank_id)

    def get_all_tanks(self) -> List[Dict[str, Any]]:
        return self._tanks_data

    def resolve_pipe_id(self, name_or_alias: str) -> Optional[str]:
        if not name_or_alias:
            return None
        cleaned = name_or_alias.lower().strip()
        if cleaned in self._pipes_by_id:
            return cleaned
        if cleaned in self._pipe_alias_map:
            return self._pipe_alias_map[cleaned]
        for pipe in self._pipes_data:
            if cleaned in pipe["name"].lower() or pipe["name"].lower() in cleaned:
                return pipe["id"]

        # Fuzzy matching
        close = self.get_close_pipe_matches(name_or_alias, limit=1)
        if close:
            best_name = close[0]
            score = fuzz.token_set_ratio(cleaned, best_name.lower())
            if score >= 75:
                for pipe in self._pipes_data:
                    if pipe["name"] == best_name:
                        return pipe["id"]

        return None

    def get_close_pipe_matches(self, name_or_alias: str, limit: int = 3) -> List[str]:
        if not name_or_alias:
            return []
        cleaned = name_or_alias.lower().strip()
        core_cleaned = cleaned.replace("sintex", "").replace("pipe", "").strip()

        candidates = [p["name"] for p in self._pipes_data]
        scored = []
        for name in candidates:
            name_core = name.lower().replace("sintex", "").strip()
            score1 = fuzz.token_set_ratio(cleaned, name.lower())
            score2 = fuzz.ratio(core_cleaned, name_core) if core_cleaned else 0
            score3 = fuzz.partial_ratio(cleaned, name.lower())
            score = max(score1, score2, score3)
            scored.append((name, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [item[0] for item in scored[:limit] if item[1] >= 40]

    def get_pipe_by_id(self, pipe_id: str) -> Optional[Dict[str, Any]]:
        return self._pipes_by_id.get(pipe_id)

    def get_all_pipes(self) -> List[Dict[str, Any]]:
        return self._pipes_data

    def get_domain_knowledge(self) -> Dict[str, Any]:
        return self._domain_knowledge

