"""
Standalone Test Suite for Sintex Tanks Catalog & Domain Knowledge.

Tests:
1. JSON integrity & schema validation for tanks_catalog.json & domain_knowledge.json.
2. Repository data loading and alias resolution (SintexCatalogRepository).
3. Service logic for model lookup, filtering, spatial fitment, comparison, and domain retrieval (SintexCatalogService).
4. LangChain tool invocation (query_sintex_catalog, get_sintex_knowledge).

Run with:
    python test_sintex_catalog.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.sintex_catalog.repository import SintexCatalogRepository
from services.sintex_catalog.service import SintexCatalogService
from services.sintex_catalog.tools import query_sintex_catalog, query_sintex_pipes, get_sintex_knowledge

PASS_COUNT = 0
FAIL_COUNT = 0


def assert_test(condition: bool, name: str, details: str = ""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  [PASS] {name}")
    else:
        FAIL_COUNT += 1
        print(f"  [FAIL] {name} - {details}")


def test_json_files():
    print("\n--- 1. Testing JSON File Integrity & Schema ---")
    data_dir = PROJECT_ROOT / "services" / "sintex_catalog" / "data"

    tanks_path = data_dir / "tanks_catalog.json"
    pipes_path = data_dir / "pipes_catalog.json"
    knowledge_path = data_dir / "domain_knowledge.json"

    assert_test(tanks_path.exists(), "tanks_catalog.json exists")
    assert_test(pipes_path.exists(), "pipes_catalog.json exists")
    assert_test(knowledge_path.exists(), "domain_knowledge.json exists")

    # Test tanks_catalog.json parsing
    with open(tanks_path, "r", encoding="utf-8") as f:
        tanks_data = json.load(f)

    assert_test("tanks" in tanks_data, "tanks_catalog.json has top-level 'tanks' key")
    tanks = tanks_data.get("tanks", [])
    assert_test(len(tanks) >= 15, f"tanks_catalog contains {len(tanks)} models (expected >= 15)")

    # Test pipes_catalog.json parsing
    with open(pipes_path, "r", encoding="utf-8") as f:
        pipes_data = json.load(f)

    assert_test("pipes" in pipes_data, "pipes_catalog.json has top-level 'pipes' key")
    pipes = pipes_data.get("pipes", [])
    assert_test(len(pipes) >= 6, f"pipes_catalog contains {len(pipes)} models (expected >= 6)")

    # Check SWRX pipe details
    swrx = next((p for p in pipes if p["id"] == "sintex_swrx"), None)
    assert_test(swrx is not None, "sintex_swrx found in pipes_catalog")
    assert_test("RATLOC" in swrx.get("anti_rodent_technology", {}).get("name", ""), "RATLOC technology defined in SWRX pipe")
    assert_test("IS 13592-2013" in swrx.get("standards_compliance", {}).get("pipes_standard", ""), "IS 13592-2013 standard present")

    # Validate each tank structure
    required_keys = ["id", "name", "tagline", "category", "key_highlights"]
    for t in tanks:
        missing = [k for k in required_keys if k not in t]
        assert_test(len(missing) == 0, f"Tank '{t.get('id', 'unknown')}' has required keys", f"Missing: {missing}")

    # Test domain_knowledge.json parsing
    with open(knowledge_path, "r", encoding="utf-8") as f:
        knowledge_data = json.load(f)

    expected_sections = [
        "company_and_contact",
        "myths_and_facts",
        "kleankit",
        "community_panel_tanks",
        "septic_vs_stp",
        "technologies",
        "swrx_pipes_knowledge",
        "sintex_pipe_portfolio"
    ]
    for section in expected_sections:
        assert_test(section in knowledge_data, f"domain_knowledge.json contains section '{section}'")

    # Check myths and facts count
    myths = knowledge_data.get("myths_and_facts", [])
    assert_test(len(myths) == 10, f"domain_knowledge contains 10 myths & facts (got {len(myths)})")

    # Check KleanKit 3 steps
    kleankit = knowledge_data.get("kleankit", {})
    steps = kleankit.get("three_steps", [])
    assert_test(len(steps) == 3, f"KleanKit has 3 steps (got {len(steps)})")


def test_repository():
    print("\n--- 2. Testing SintexCatalogRepository & Alias Resolution ---")
    repo = SintexCatalogRepository.get_instance()

    all_tanks = repo.get_all_tanks()
    assert_test(len(all_tanks) > 0, "Repository loaded tanks successfully")

    # Test alias resolution
    test_cases = [
        ("pure", "sintex_pure"),
        ("sintex pure", "sintex_pure"),
        ("pure+", "sintex_pure_plus"),
        ("pure plus", "sintex_pure_plus"),
        ("plus", "sintex_pure_plus"),
        ("sintex plus", "sintex_pure_plus"),
        ("eterno", "sintex_eterno"),
        ("tatva", "sintex_tatva"),
        ("trupuf", "sintex_trupuf"),
        ("turpuf", "sintex_trupuf"),
        ("sintex turpuf", "sintex_trupuf"),
        ("puf", "sintex_trupuf"),
        ("neo", "sintex_neo"),
        ("smart", "sintex_smart"),
        ("reno", "sintex_reno"),
        ("titus", "sintex_titus"),
        ("hero", "sintex_hero"),
        ("ace", "sintex_ace"),
        ("side hatch", "sintex_ace"),
        ("classic", "sintex_classic"),
        ("isi", "sintex_isi"),
        ("loft", "sintex_loft"),
        ("sump", "sintex_underground_sump"),
        ("frp", "sintex_underground_frp"),
        ("panel tank", "sintex_pure_community_panel_tank"),
        ("community", "sintex_pure_community_panel_tank"),
        ("septic", "sintex_advanced_septic_tank"),
        ("ast", "sintex_advanced_septic_tank"),
        ("stp", "sintex_packaged_stp"),
    ]

    for alias, expected_id in test_cases:
        resolved = repo.resolve_tank_id(alias)
        assert_test(resolved == expected_id, f"Alias '{alias}' -> '{expected_id}'", f"Got: {resolved}")

    # Test pipe alias resolution
    pipe_test_cases = [
        ("swrx", "sintex_swrx"),
        ("sintex swrx", "sintex_swrx"),
        ("swrx pro", "sintex_swrx"),
        ("ratloc", "sintex_swrx"),
        ("anti rat", "sintex_swrx"),
        ("type a", "sintex_swrx_type_a"),
        ("type b", "sintex_swrx_type_b"),
        ("hotx", "sintex_hotx"),
        ("coolx", "sintex_coolx"),
        ("groundx", "sintex_groundx"),
        ("agrix", "sintex_agrix"),
        ("reclaimx", "sintex_reclaimx"),
    ]
    for p_alias, p_expected_id in pipe_test_cases:
        p_resolved = repo.resolve_pipe_id(p_alias)
        assert_test(p_resolved == p_expected_id, f"Pipe Alias '{p_alias}' -> '{p_expected_id}'", f"Got: {p_resolved}")

    # Test close matches suggestion
    close = repo.get_close_matches("sintex pluss", limit=3)
    assert_test("Sintex Pure+" in close, "get_close_matches('sintex pluss') suggests 'Sintex Pure+'")


def test_service_lookups():
    print("\n--- 3. Testing SintexCatalogService Lookups & Logic ---")
    service = SintexCatalogService()

    # Model lookup with full specs
    res = service.get_tank_details("Sintex Pure")
    assert_test(res.get("status") == "success", "get_tank_details('Sintex Pure') returns success")
    assert_test(res.get("data", {}).get("warranty_years") == 15, "Sintex Pure warranty is 15 years")

    # Direct resolution of "sintex plus"
    res_plus = service.get_tank_details("sintex plus")
    assert_test(res_plus.get("status") == "success", "get_tank_details('sintex plus') resolves successfully")
    assert_test(res_plus.get("data", {}).get("name") == "Sintex Pure+", "'sintex plus' resolved to Sintex Pure+")

    # Specific capacity lookup (1000L)
    res_1000 = service.get_tank_details("Sintex Pure", capacity_litres=1000)
    specs = res_1000.get("data", {}).get("specifications", [])
    assert_test(len(specs) == 1 and specs[0]["capacity_litres"] == 1000, "Specific 1000L specs returned")
    assert_test(specs[0].get("sku_code") == "HSWS-0100-01-PURE", "Correct SKU code for 1000L Pure")

    # Nonexistent capacity handling
    res_nonexistent = service.get_tank_details("Sintex Pure", capacity_litres=999)
    assert_test("specifications_note" in res_nonexistent.get("data", {}), "Note returned for nonexistent capacity")

    # Nonexistent model with suggestions
    res_bad = service.get_tank_details("NonExistentTank999")
    assert_test(res_bad.get("status") == "not_found", "Unrecognized model returns not_found")
    assert_test("suggested_models" in res_bad or "available_models" in res_bad, "Suggestions returned for unrecognized model")

    # Pipe lookup: Sintex SWRX
    res_swrx = service.get_pipe_details("Sintex SWRX")
    assert_test(res_swrx.get("status") == "success", "get_pipe_details('Sintex SWRX') returns success")
    assert_test("RATLOC" in res_swrx.get("data", {}).get("anti_rodent_technology", {}).get("name", ""), "SWRX pipe has RATLOC technology")

    # Pipe lookup via get_tank_details fallback
    res_pipe_fallback = service.get_tank_details("swrx pro")
    assert_test(res_pipe_fallback.get("status") == "success", "get_tank_details('swrx pro') resolves via pipe fallback")

    # Pipe Type A lookup
    res_type_a = service.get_pipe_details("Type A")
    assert_test(res_type_a.get("status") == "success", "get_pipe_details('Type A') resolves")
    assert_test("Blue" in res_type_a.get("data", {}).get("marking_colour", ""), "Type A pipe has blue marking")


def test_service_filtering():
    print("\n--- 4. Testing Filtering & Feature Queries ---")
    service = SintexCatalogService()

    # Filter by warranty (>= 15 years)
    res_15 = service.filter_tanks(min_warranty_years=15)
    names_15 = [t["name"] for t in res_15.get("matching_tanks", [])]
    assert_test("Sintex Eterno" in names_15, "Eterno in >=15 year warranty filter")
    assert_test("Sintex Pure" in names_15, "Pure in >=15 year warranty filter")
    assert_test("Sintex Neo" not in names_15, "Neo excluded from >=15 year warranty filter")

    # Filter by 4P Protection
    res_4p = service.filter_tanks(features=["4p"])
    names_4p = [t["name"] for t in res_4p.get("matching_tanks", [])]
    assert_test("Sintex Eterno" in names_4p and "Sintex Pure" in names_4p, "4P tanks matched correctly")
    assert_test("Sintex Neo" not in names_4p, "Non-4P tank excluded")

    # Filter by Side Hatch
    res_sh = service.filter_tanks(features=["side_hatch"])
    names_sh = [t["name"] for t in res_sh.get("matching_tanks", [])]
    assert_test("Sintex Ace" in names_sh and "Sintex Smart" in names_sh, "Side hatch tanks matched (Ace & Smart)")

    # Filter by Color
    res_black = service.filter_tanks(color="Black")
    names_black = [t["name"] for t in res_black.get("matching_tanks", [])]
    assert_test("Sintex Classic" in names_black and "Sintex ISI" in names_black, "Black tanks matched (Classic, ISI, Reno)")


def test_service_dimension_recommendations():
    print("\n--- 5. Testing Space Fitment & Dimension Recommendations ---")
    service = SintexCatalogService()

    # Overhead clearance: Height <= 1000mm, Diameter <= 1000mm
    rec = service.recommend_by_dimensions(max_height_mm=1000, max_width_or_diameter_mm=1000)
    assert_test(rec.get("status") == "success", "recommend_by_dimensions returned success")
    matches = rec.get("suitable_tanks", [])
    assert_test(len(matches) > 0, f"Found {len(matches)} tanks fitting <= 1000mm height & diameter")
    for m in matches:
        assert_test(m["height_mm"] <= 1000, f"{m['model']} ({m['capacity_litres']}L) height {m['height_mm']}mm <= 1000mm")
        assert_test(m["diameter_mm"] <= 1000, f"{m['model']} ({m['capacity_litres']}L) diameter {m['diameter_mm']}mm <= 1000mm")

    # Rectangular Loft tank fitment: Height <= 400mm
    loft_rec = service.recommend_by_dimensions(max_height_mm=400, tank_shape="rectangular_loft")
    loft_matches = loft_rec.get("suitable_tanks", [])
    assert_test(len(loft_matches) > 0, f"Found {len(loft_matches)} loft tanks fitting <= 400mm height")
    for m in loft_matches:
        assert_test(m["shape"] == "Rectangular Loft", "Matched tank is Rectangular Loft")
        assert_test(m["height_mm"] <= 400, f"Loft height {m['height_mm']}mm <= 400mm")


def test_service_comparison():
    print("\n--- 6. Testing Side-by-Side Model Comparison ---")
    service = SintexCatalogService()

    res = service.compare_tanks(["Sintex Eterno", "Sintex Pure", "Sintex Neo"])
    assert_test(res.get("status") == "success", "compare_tanks returns success")
    comp = res.get("comparison", [])
    assert_test(len(comp) == 3, "Compared 3 models")
    eterno = next(c for c in comp if c["name"] == "Sintex Eterno")
    pure = next(c for c in comp if c["name"] == "Sintex Pure")
    neo = next(c for c in comp if c["name"] == "Sintex Neo")

    assert_test(eterno["warranty_years"] == 50, "Eterno warranty 50 years")
    assert_test(pure["warranty_years"] == 15, "Pure warranty 15 years")
    assert_test(neo["warranty_years"] == 3, "Neo warranty 3 years")


def test_domain_knowledge():
    print("\n--- 7. Testing Domain Knowledge Queries ---")
    service = SintexCatalogService()

    # Myths and facts
    myths = service.get_domain_knowledge("myths")
    assert_test(myths.get("status") == "success", "Retrieved myths by alias 'myths'")
    assert_test(len(myths.get("data", [])) == 10, "10 myths returned")

    # KleanKit
    klean = service.get_domain_knowledge("cleaning")
    assert_test(klean.get("status") == "success", "Retrieved KleanKit by alias 'cleaning'")
    assert_test("three_steps" in klean.get("data", {}), "KleanKit has 3 steps")

    # STP vs Septic
    stp = service.get_domain_knowledge("stp")
    assert_test(stp.get("status") == "success", "Retrieved STP vs Septic by alias 'stp'")
    assert_test("packaged_stp" in stp.get("data", {}), "Contains packaged_stp")

    # Contact & company
    contact = service.get_domain_knowledge("contact")
    assert_test(contact.get("status") == "success", "Retrieved company info by alias 'contact'")
    assert_test(contact.get("data", {}).get("toll_free_number") == "1800-121-2764", "Toll-free number matches")

    # SWRX pipes domain knowledge
    swrx_know = service.get_domain_knowledge("swrx")
    assert_test(swrx_know.get("status") == "success", "Retrieved SWRX knowledge by alias 'swrx'")
    assert_test("RATLOC" in swrx_know.get("data", {}).get("anti_rodent_protection", ""), "SWRX knowledge contains RATLOC")

    # RatLoc technology domain knowledge
    ratloc_know = service.get_domain_knowledge("ratloc")
    assert_test(ratloc_know.get("status") == "success", "Retrieved RATLOC by alias 'ratloc'")

    # Sintex pipe portfolio
    portfolio_know = service.get_domain_knowledge("pipe_portfolio")
    assert_test(portfolio_know.get("status") == "success", "Retrieved Sintex pipe portfolio")


async def test_langchain_tools():
    print("\n--- 8. Testing Async LangChain Tools ---")

    # Test query_sintex_catalog tool directly (tank)
    raw_res = await query_sintex_catalog.ainvoke({"model_name": "Eterno", "capacity_litres": 1000})
    parsed = json.loads(raw_res)
    assert_test(parsed.get("status") == "success", "query_sintex_catalog ainvoke returns success for Eterno")
    assert_test(parsed.get("data", {}).get("name") == "Sintex Eterno", "query_sintex_catalog returned Sintex Eterno")

    # Test query_sintex_catalog tool directly with pipe model name
    raw_cat_pipe = await query_sintex_catalog.ainvoke({"model_name": "Sintex SWRX"})
    parsed_cat_pipe = json.loads(raw_cat_pipe)
    assert_test(parsed_cat_pipe.get("status") == "success", "query_sintex_catalog handles pipe model 'Sintex SWRX'")

    # Test query_sintex_pipes tool directly
    raw_pipe = await query_sintex_pipes.ainvoke({"model_name": "Sintex SWRX", "pipe_type": "Type A"})
    parsed_pipe = json.loads(raw_pipe)
    assert_test(parsed_pipe.get("status") == "success", "query_sintex_pipes ainvoke returns success")
    assert_test(parsed_pipe.get("data", {}).get("id") == "sintex_swrx", "query_sintex_pipes returned Sintex SWRX")

    # Test get_sintex_knowledge tool directly (kleankit)
    raw_know = await get_sintex_knowledge.ainvoke({"topic": "kleankit"})
    parsed_know = json.loads(raw_know)
    assert_test(parsed_know.get("status") == "success", "get_sintex_knowledge ainvoke returns success for kleankit")
    assert_test("Sintex Kleankit" in parsed_know.get("data", {}).get("name", ""), "Returned Sintex Kleankit data")

    # Test get_sintex_knowledge tool directly (swrx)
    raw_swrx = await get_sintex_knowledge.ainvoke({"topic": "swrx"})
    parsed_swrx = json.loads(raw_swrx)
    assert_test(parsed_swrx.get("status") == "success", "get_sintex_knowledge ainvoke returns success for swrx")


def main():
    print("=" * 60)
    print("SINTEX CATALOG & DOMAIN KNOWLEDGE TEST SUITE")
    print("=" * 60)

    test_json_files()
    test_repository()
    test_service_lookups()
    test_service_filtering()
    test_service_dimension_recommendations()
    test_service_comparison()
    test_domain_knowledge()
    asyncio.run(test_langchain_tools())

    print("\n" + "=" * 60)
    print(f"SUMMARY: {PASS_COUNT} PASSED, {FAIL_COUNT} FAILED")
    print("=" * 60)

    if FAIL_COUNT > 0:
        sys.exit(1)
    else:
        print("ALL TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
