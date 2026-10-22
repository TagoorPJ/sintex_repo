"""
Tool definitions for LangGraph/LangChain Agents to query the Sintex catalog and knowledge base.
Decorated with @tool for direct binding in app/chatbot.py.
"""

from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from langchain.tools import tool
from .service import SintexCatalogService

_service = SintexCatalogService()

@tool("query_sintex_catalog")
async def query_sintex_catalog(
    model_name: Optional[str] = None,
    capacity_litres: Optional[int] = None,
    min_warranty_years: Optional[int] = None,
    features: Optional[List[str]] = None,
    color: Optional[str] = None,
    max_height_mm: Optional[float] = None,
    max_width_or_diameter_mm: Optional[float] = None,
    max_length_mm: Optional[float] = None,
    tank_shape: Optional[str] = None,
    compare_models: Optional[List[str]] = None
) -> str:
    """
    Tool Name: query_sintex_catalog

    Purpose:
    Search, filter, or retrieve exact verified specifications, dimensions, SKU codes,
    and warranties for all Sintex water tanks from the official catalog.

    Use this tool whenever the user asks about:
    - Specific Sintex water tank models (Eterno, Pure, Pure+, Tatva, Trupuf, Neo, Smart, Reno, Titus, Hero, Ace, Classic, ISI, Loft, Sumps, FRP, Community Panel).
    - Dimensions: height (mm/in), diameter (mm/in), hatch opening (mm/in), or length/width for loft tanks.
    - Exact SKU codes for any capacity (e.g., 500L, 750L, 1000L, 1500L, 2000L, etc.).
    - Physical space/clearance fitment (e.g. "my height limit is 1200 mm, what tank will fit?").
    - Filtering tanks by features (anti_bacterial, anti_viral, 4p, threaded_lid, side_hatch, double_layer_lids, etc.).
    - Comparing two or more Sintex tanks side-by-side.

    Parameters:
    - model_name: Tank model name or alias (e.g., 'Sintex Pure', 'Eterno', 'Trupuf', 'Ace', 'Titus', 'Classic', 'Loft', 'Sump').
    - capacity_litres: Specific capacity to check in litres (e.g., 500, 750, 1000, 1500, 2000, 5000).
    - min_warranty_years: Minimum warranty required in years (e.g., 3, 5, 10, 15, 50).
    - features: List of features to filter by (e.g., ['anti_bacterial', 'threaded_lid', 'side_hatch', 'anti_algae', '4p']).
    - color: Desired color ('White', 'Blue', 'Yellow', 'Green', 'Black').
    - max_height_mm: Maximum allowable height in millimeters.
    - max_width_or_diameter_mm: Maximum allowable width or diameter in millimeters.
    - max_length_mm: Maximum allowable length in millimeters (for rectangular loft tanks).
    - tank_shape: 'overhead_cylindrical' or 'rectangular_loft'.
    - compare_models: List of model names to compare (e.g., ['Sintex Pure', 'Sintex Pure+']).
    """
    try:
        # Case 1: Comparison between multiple models
        if compare_models and len(compare_models) > 1:
            res = _service.compare_tanks(compare_models)
            return json.dumps(res, ensure_ascii=False, indent=2)

        # Case 2: Dimension / Space clearance constraint
        if max_height_mm or max_width_or_diameter_mm or max_length_mm:
            res = _service.recommend_by_dimensions(
                max_height_mm=max_height_mm,
                max_width_or_diameter_mm=max_width_or_diameter_mm,
                max_length_mm=max_length_mm,
                min_capacity_litres=capacity_litres,
                tank_shape=tank_shape
            )
            return json.dumps(res, ensure_ascii=False, indent=2)

        # Case 3: Specific Model Lookup
        if model_name:
            res = _service.get_tank_details(model_name, capacity_litres=capacity_litres)
            return json.dumps(res, ensure_ascii=False, indent=2)

        # Case 4: Group Filter by Features, Warranty, Color, or Capacity
        res = _service.filter_tanks(
            min_warranty_years=min_warranty_years,
            features=features,
            color=color,
            capacity_litres=capacity_litres
        )
        return json.dumps(res, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)


@tool("get_sintex_knowledge")
async def get_sintex_knowledge(topic: Optional[str] = None) -> str:
    """
    Tool Name: get_sintex_knowledge

    Purpose:
    Retrieve verified technical domain knowledge, company background, myths & facts,
    and non-overhead solutions from the official Sintex documentation.

    Use this tool whenever the user asks about:
    - Myths vs Facts: Why more layers (4, 5, 6, 7 layers) don't add strength, why heavier competitor tanks are unsafe due to calcium carbonate fillers, why detergent is hazardous to clean tanks, why virgin food-grade plastic matters.
    - Sintex KleanKit: Complete tank cleaning kit, benefits, 3-step usage (Remove, Rinse, Cleanse).
    - Large Commercial Solutions: Sintex Pure Community Panel Tanks (up to 16 lakh litres, replaces RCC tanks).
    - Waste Water Treatment: Sintex Advanced Septic Tanks (70% BOD reduction, no power) vs Packaged STP (90-95% BOD reduction, grey water reuse).
    - Special technologies: Active Silver 4P protection, PUF 50mm insulation in Trupuf (-20°C to 50°C), ARPS in Tatva.
    - Company details: Toll-free number (1800-121-2764), email (sintex_support@welspun.com), and Welspun legacy.

    Parameters:
    - topic: One of ['myths_and_facts', 'kleankit', 'community_panel_tanks', 'septic_vs_stp', 'technologies', 'company_and_contact']
    """
    try:
        res = _service.get_domain_knowledge(topic=topic)
        return json.dumps(res, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)


sintex_tools = [query_sintex_catalog, get_sintex_knowledge]
