"""
Core service logic for querying Sintex tanks, comparing models,
filtering by technical parameters, and spatial fitment calculations.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Union
from .repository import SintexCatalogRepository

class SintexCatalogService:
    def __init__(self, repository: Optional[SintexCatalogRepository] = None) -> None:
        self.repo = repository or SintexCatalogRepository.get_instance()

    def get_tank_details(
        self,
        tank_name: str,
        capacity_litres: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Retrieves full specifications, highlights, warranty, and dimensions for a specific tank model.
        """
        tank_id = self.repo.resolve_tank_id(tank_name)
        if not tank_id:
            available_names = [t["name"] for t in self.repo.get_all_tanks()]
            return {
                "status": "not_found",
                "message": f"Could not find model matching '{tank_name}'.",
                "available_models": available_names
            }

        tank = self.repo.get_tank_by_id(tank_id)
        if not tank:
            return {"status": "not_found", "message": f"Tank data for '{tank_id}' not found."}

        result = dict(tank)
        specs = tank.get("specifications", [])

        if capacity_litres is not None and specs:
            matching_specs = [
                s for s in specs if s.get("capacity_litres") == capacity_litres
            ]
            if matching_specs:
                result["specifications"] = matching_specs
            else:
                available_caps = [s.get("capacity_litres") for s in specs]
                result["specifications_note"] = (
                    f"Requested capacity {capacity_litres}L is not available for {tank['name']}. "
                    f"Available capacities are: {available_caps} litres."
                )

        return {"status": "success", "data": result}

    def filter_tanks(
        self,
        min_warranty_years: Optional[int] = None,
        features: Optional[List[str]] = None,
        color: Optional[str] = None,
        manufacturing_process: Optional[str] = None,
        category: Optional[str] = None,
        capacity_litres: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Filters tanks matching multiple criteria simultaneously.
        """
        all_tanks = self.repo.get_all_tanks()
        matches = []

        feature_keys_map = {
            "anti_viral": lambda t: t.get("protections", {}).get("anti_viral", False),
            "anti_bacterial": lambda t: t.get("protections", {}).get("anti_bacterial", False),
            "anti_algae": lambda t: t.get("protections", {}).get("anti_algae", False),
            "anti_fungal": lambda t: t.get("protections", {}).get("anti_fungal", False),
            "4p": lambda t: all(t.get("protections", {}).get(k, False) for k in ["anti_viral", "anti_bacterial", "anti_algae", "anti_fungal"]),
            "threaded_lid": lambda t: t.get("threaded_lid", False),
            "side_hatch": lambda t: t.get("side_hatch", False),
            "double_layer_lids": lambda t: t.get("double_layer_lids", False),
            "rohs_compliant": lambda t: t.get("rohs_compliant", False),
            "food_grade": lambda t: t.get("food_grade_plastic", False),
            "virgin_plastic": lambda t: t.get("virgin_plastic", False),
        }

        for tank in all_tanks:
            if min_warranty_years is not None:
                warranty = tank.get("warranty_years", 0)
                if warranty < min_warranty_years:
                    continue

            if category and category.lower() not in tank.get("category", "").lower():
                continue

            if manufacturing_process and manufacturing_process.lower() not in tank.get("manufacturing_process", "").lower():
                continue

            if color:
                avail_colors = [c.lower() for c in tank.get("available_colors", [])]
                if color.lower() not in avail_colors:
                    continue

            if features:
                failed_feature = False
                for f in features:
                    norm_f = f.lower().strip().replace("-", "_").replace(" ", "_")
                    check_func = feature_keys_map.get(norm_f)
                    if check_func:
                        if not check_func(tank):
                            failed_feature = True
                            break
                    else:
                        found_in_highlights = any(
                            norm_f in h.lower() for h in tank.get("key_highlights", [])
                        )
                        if not found_in_highlights:
                            failed_feature = True
                            break
                if failed_feature:
                    continue

            if capacity_litres is not None:
                specs = tank.get("specifications", [])
                caps = [s.get("capacity_litres") for s in specs]
                if not caps and "capacities_litres" in tank:
                    caps = tank.get("capacities_litres", [])
                if capacity_litres not in caps:
                    continue

            caps_list = [s.get("capacity_litres") for s in tank.get("specifications", [])]
            if not caps_list and "capacities_litres" in tank:
                caps_list = tank.get("capacities_litres", [])

            matches.append({
                "id": tank["id"],
                "name": tank["name"],
                "tagline": tank["tagline"],
                "category": tank.get("category"),
                "warranty_years": tank.get("warranty_years"),
                "manufacturing_process": tank.get("manufacturing_process"),
                "available_colors": tank.get("available_colors", []),
                "protections": tank.get("protections", {}),
                "threaded_lid": tank.get("threaded_lid", False),
                "side_hatch": tank.get("side_hatch", False),
                "capacities": caps_list
            })

        return {
            "status": "success",
            "count": len(matches),
            "matching_tanks": matches
        }

    def recommend_by_dimensions(
        self,
        max_height_mm: Optional[float] = None,
        max_width_or_diameter_mm: Optional[float] = None,
        max_length_mm: Optional[float] = None,
        min_capacity_litres: Optional[int] = None,
        tank_shape: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Finds exact tank sizes that fit within physical height, width, and length constraints.
        """
        all_tanks = self.repo.get_all_tanks()
        suitable_options = []

        for tank in all_tanks:
            shape = tank.get("shape", "overhead_cylindrical")
            if tank_shape and tank_shape.lower() not in shape.lower():
                continue

            specs = tank.get("specifications", [])
            for row in specs:
                capacity = row.get("capacity_litres", 0)
                if min_capacity_litres and capacity < min_capacity_litres:
                    continue

                if shape == "rectangular_loft":
                    h = row.get("height_mm", 0)
                    w = row.get("width_mm", 0)
                    l = row.get("length_mm", 0)

                    if max_height_mm and h > max_height_mm:
                        continue
                    if max_width_or_diameter_mm and w > max_width_or_diameter_mm:
                        continue
                    if max_length_mm and l > max_length_mm:
                        continue

                    suitable_options.append({
                        "model": tank["name"],
                        "category": tank.get("category"),
                        "shape": "Rectangular Loft",
                        "capacity_litres": capacity,
                        "length_mm": l,
                        "length_inches": row.get("length_inches"),
                        "width_mm": w,
                        "width_inches": row.get("width_inches"),
                        "height_mm": h,
                        "height_inches": row.get("height_inches"),
                        "sku_code": row.get("sku_code", "-"),
                        "warranty_years": tank.get("warranty_years")
                    })

                else:
                    h = row.get("height_mm", 0)
                    dia = row.get("diameter_mm", 0)

                    if max_height_mm and h > max_height_mm:
                        continue
                    if max_width_or_diameter_mm and dia > max_width_or_diameter_mm:
                        continue

                    suitable_options.append({
                        "model": tank["name"],
                        "category": tank.get("category"),
                        "shape": "Cylindrical Overhead",
                        "capacity_litres": capacity,
                        "diameter_mm": dia,
                        "diameter_inches": row.get("diameter_inches"),
                        "height_mm": h,
                        "height_inches": row.get("height_inches"),
                        "diameter_hatch_mm": row.get("diameter_hatch_mm"),
                        "sku_code": row.get("sku_code", "-"),
                        "warranty_years": tank.get("warranty_years")
                    })

        suitable_options.sort(
            key=lambda x: (
                -x.get("capacity_litres", 0),
                -(x.get("warranty_years") or 0)
            )
        )

        return {
            "status": "success",
            "matches_found": len(suitable_options),
            "suitable_tanks": suitable_options
        }

    def compare_tanks(self, tank_names: List[str]) -> Dict[str, Any]:
        """
        Provides side-by-side comparison data for two or more tanks.
        """
        models_data = []
        for name in tank_names:
            detail = self.get_tank_details(name)
            if detail.get("status") == "success":
                tank = detail["data"]
                caps = [s.get("capacity_litres") for s in tank.get("specifications", [])]
                if not caps and "capacities_litres" in tank:
                    caps = tank.get("capacities_litres", [])
                models_data.append({
                    "name": tank["name"],
                    "category": tank.get("category"),
                    "warranty_years": tank.get("warranty_years"),
                    "process": tank.get("manufacturing_process"),
                    "colors": tank.get("available_colors", []),
                    "protections": tank.get("protections", {}),
                    "threaded_lid": tank.get("threaded_lid", False),
                    "side_hatch": tank.get("side_hatch", False),
                    "capacities": caps,
                    "highlights": tank.get("key_highlights", [])[:3]
                })

        return {
            "status": "success",
            "comparison": models_data
        }

    def get_domain_knowledge(self, topic: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves company info, myths & facts, KleanKit, STP/septic, or technologies.
        """
        knowledge = self.repo.get_domain_knowledge()
        if not topic:
            return {"status": "success", "available_topics": list(knowledge.keys()), "data": knowledge}

        topic_clean = topic.lower().strip()
        if topic_clean in knowledge:
            return {"status": "success", "topic": topic_clean, "data": knowledge[topic_clean]}

        topic_map = {
            "myths": "myths_and_facts",
            "facts": "myths_and_facts",
            "cleaning": "kleankit",
            "klean": "kleankit",
            "kleankit": "kleankit",
            "septic": "septic_vs_stp",
            "stp": "septic_vs_stp",
            "panel": "community_panel_tanks",
            "community": "community_panel_tanks",
            "contact": "company_and_contact",
            "support": "company_and_contact",
            "phone": "company_and_contact",
            "email": "company_and_contact",
            "tech": "technologies",
            "active_silver": "technologies",
            "puf": "technologies"
        }

        matched_key = topic_map.get(topic_clean)
        if matched_key and matched_key in knowledge:
            return {"status": "success", "topic": matched_key, "data": knowledge[matched_key]}

        return {
            "status": "not_found",
            "message": f"Topic '{topic}' not found.",
            "available_topics": list(knowledge.keys())
        }
