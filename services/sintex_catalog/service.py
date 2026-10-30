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
            # Check if this query corresponds to a Sintex pipe product
            pipe_id = self.repo.resolve_pipe_id(tank_name)
            if pipe_id:
                return self.get_pipe_details(pipe_id)

            close_matches = self.repo.get_close_matches(tank_name, limit=3)
            pipe_matches = self.repo.get_close_pipe_matches(tank_name, limit=2)
            all_suggestions = list(dict.fromkeys(close_matches + pipe_matches))
            available_names = [t["name"] for t in self.repo.get_all_tanks()]
            return {
                "status": "not_found",
                "message": f"Could not find model matching '{tank_name}'.",
                "did_you_mean": all_suggestions,
                "suggested_models": all_suggestions,
                "available_models": available_names[:6]
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

    def get_pipe_details(
        self,
        pipe_name: str,
        pipe_type: Optional[str] = None,
        joint_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieves full specifications, standards, jointing systems, and highlights for Sintex SWRX pipes.
        """
        pipe_id = self.repo.resolve_pipe_id(pipe_name)
        if not pipe_id:
            close_matches = self.repo.get_close_pipe_matches(pipe_name, limit=3)
            all_pipes = [p["name"] for p in self.repo.get_all_pipes()]
            return {
                "status": "not_found",
                "message": f"Could not find pipe model matching '{pipe_name}'.",
                "did_you_mean": close_matches,
                "suggested_models": close_matches,
                "available_models": all_pipes
            }

        pipe = self.repo.get_pipe_by_id(pipe_id)
        if not pipe:
            return {"status": "not_found", "message": f"Pipe data for '{pipe_id}' not found."}

        res = dict(pipe)

        # Filter by Type A vs Type B if specified
        if pipe_type and "pipe_types" in res:
            req_type = pipe_type.lower().strip()
            filtered_types = [
                pt for pt in res["pipe_types"]
                if req_type in pt["type"].lower() or req_type in pt["purpose"].lower()
            ]
            if filtered_types:
                res["pipe_types"] = filtered_types

        # Filter connection systems if specified (ringfit vs selfit)
        if joint_type and "connection_systems" in res:
            req_joint = joint_type.lower().strip()
            if "ring" in req_joint:
                res["focused_connection_system"] = res["connection_systems"].get("ringfit")
            elif "sol" in req_joint or "self" in req_joint:
                res["focused_connection_system"] = res["connection_systems"].get("selfit")

        return {"status": "success", "data": res}

    def filter_pipes(
        self,
        pipe_type: Optional[str] = None,
        joint_type: Optional[str] = None,
        feature: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Filters Sintex pipe offerings by application, jointing type, or features.
        """
        all_pipes = self.repo.get_all_pipes()
        matches = []

        for p in all_pipes:
            if pipe_type:
                req_t = pipe_type.lower().strip()
                if req_t not in p.get("name", "").lower() and req_t not in p.get("category", "").lower():
                    # Check internal pipe_types
                    has_sub = any(req_t in pt["type"].lower() for pt in p.get("pipe_types", []))
                    if not has_sub:
                        continue

            if joint_type and "connection_systems" in p:
                req_j = joint_type.lower().strip()
                if "ring" in req_j and "ringfit" not in p["connection_systems"]:
                    continue
                if ("sol" in req_j or "self" in req_j) and "selfit" not in p["connection_systems"]:
                    continue

            if feature:
                req_f = feature.lower().strip()
                highlights = [h.lower() for h in p.get("key_highlights", [])]
                if not any(req_f in h for h in highlights):
                    continue

            matches.append({
                "id": p["id"],
                "name": p["name"],
                "tagline": p.get("tagline"),
                "category": p.get("category"),
                "highlights": p.get("key_highlights", [])[:3]
            })

        return {
            "status": "success",
            "count": len(matches),
            "matching_pipes": matches
        }

    def get_domain_knowledge(self, topic: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves company info, myths & facts, KleanKit, STP/septic, technologies, or SWRX pipes.
        """
        knowledge = self.repo.get_domain_knowledge()
        if not topic:
            return {"status": "success", "available_topics": list(knowledge.keys()), "data": knowledge}

        topic_clean = topic.lower().strip().replace("-", "_").replace(" ", "_")
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
            "puf": "technologies",
            "swrx": "swrx_pipes_knowledge",
            "swrx_pipes": "swrx_pipes_knowledge",
            "swr": "swrx_pipes_knowledge",
            "swr_pipe": "swrx_pipes_knowledge",
            "swr_pipes": "swrx_pipes_knowledge",
            "pipe": "swrx_pipes_knowledge",
            "pipes": "swrx_pipes_knowledge",
            "ratloc": "swrx_pipes_knowledge",
            "rat_loc": "swrx_pipes_knowledge",
            "anti_rat": "swrx_pipes_knowledge",
            "antirat": "swrx_pipes_knowledge",
            "anti_rodent": "swrx_pipes_knowledge",
            "type_a": "swrx_pipes_knowledge",
            "type_b": "swrx_pipes_knowledge",
            "ringfit": "swrx_pipes_knowledge",
            "selfit": "swrx_pipes_knowledge",
            "solfit": "swrx_pipes_knowledge",
            "solvent_cement": "swrx_pipes_knowledge",
            "lubricant": "swrx_pipes_knowledge",
            "pipe_portfolio": "sintex_pipe_portfolio",
            "pipe_range": "sintex_pipe_portfolio",
            "pipe_systems": "sintex_pipe_portfolio"
        }

        matched_key = topic_map.get(topic_clean)
        if matched_key and matched_key in knowledge:
            return {"status": "success", "topic": matched_key, "data": knowledge[matched_key]}

        return {
            "status": "not_found",
            "message": f"Topic '{topic}' not found.",
            "available_topics": list(knowledge.keys())
        }

