import json

from src.servers.pharmacy.core.dispatcher import Dispatcher
from src.servers.pharmacy.core.domain import catalog, interactions, inventory, orders, triage
from src.servers.pharmacy.core.domain.errors import PharmacyError
from src.servers.pharmacy.core.tools import TOOLS


def get_tool(name: str):
    return next(t for t in TOOLS if t.name == name)


# --- triage -----------------------------------------------------------------


def test_assess_symptoms_matches_common_cold():
    result = triage.assess_symptoms(symptoms=["runny nose", "sore throat"], duration_days=2, age=28)
    assert "common_cold" in result["likely_conditions"]
    assert result["severity"] == "mild"
    assert result["red_flags"] == []


def test_assess_symptoms_flags_chest_pain_as_urgent():
    result = triage.assess_symptoms(symptoms=["chest pain", "shortness of breath"], duration_days=1, age=45)
    assert result["severity"] == "urgent"
    assert result["red_flags"]


def test_assess_symptoms_flags_infants():
    result = triage.assess_symptoms(symptoms=["fever"], duration_days=1, age=1)
    assert result["severity"] == "urgent"
    assert any("infants" in flag for flag in result["red_flags"])


def test_assess_symptoms_flags_prolonged_duration():
    result = triage.assess_symptoms(symptoms=["cough"], duration_days=15, age=30)
    assert result["severity"] == "urgent"
    assert any("more than 10 days" in flag for flag in result["red_flags"])


# --- catalog ------------------------------------------------------------------


def test_search_medications_excludes_prescription_only_by_default():
    results = catalog.search_medications(therapeutic_class="antibiotic")
    assert results == []


def test_search_medications_finds_analgesics():
    results = catalog.search_medications(therapeutic_class="analgesic")
    skus = {r["sku"] for r in results}
    assert "PARA500" in skus
    assert "IBU400" in skus


def test_get_medication_details_unknown_sku_raises():
    try:
        catalog.get_medication_details("NOPE")
        assert False, "expected PharmacyError"
    except PharmacyError:
        pass


# --- interactions ---------------------------------------------------------------


def test_check_interactions_blocks_ibuprofen_with_warfarin():
    result = interactions.check_interactions(
        candidate_skus=["IBU400"], current_medications=["warfarin"]
    )
    assert result["safe_to_recommend"] is False
    assert result["blocking"]


def test_check_interactions_flags_allergy_conflict():
    result = interactions.check_interactions(candidate_skus=["PARA500"], allergies=["paracetamol"])
    assert result["safe_to_recommend"] is False
    assert result["allergy_conflicts"]


def test_check_interactions_clean_case_is_safe():
    result = interactions.check_interactions(candidate_skus=["LORA10"], current_medications=[], allergies=[])
    assert result["safe_to_recommend"] is True
    assert result["blocking"] == []
    assert result["allergy_conflicts"] == []


# --- inventory --------------------------------------------------------------


def test_check_stock_single_branch():
    result = inventory.check_stock("PARA500", branch_id="zona10")
    assert len(result["branches"]) == 1
    assert result["branches"][0]["branch_id"] == "zona10"


def test_check_stock_all_branches():
    result = inventory.check_stock("PARA500")
    assert len(result["branches"]) == 3


# --- orders -------------------------------------------------------------------


def test_create_order_refuses_prescription_only_without_id():
    try:
        orders.create_order(items=[{"sku": "AMOX500", "quantity": 1}], branch_id="zona10")
        assert False, "expected PharmacyError"
    except PharmacyError as exc:
        assert "prescription" in str(exc).lower()


def test_create_order_succeeds_and_decrements_stock():
    before = inventory.check_stock("PARA500", branch_id="zona1")["branches"][0]["quantity"]
    order = orders.create_order(
        items=[{"sku": "PARA500", "quantity": 1}], branch_id="zona1", fulfillment="pickup"
    )
    after = inventory.check_stock("PARA500", branch_id="zona1")["branches"][0]["quantity"]

    assert order["status"] == "confirmed"
    assert order["total"] == order["items"][0]["line_total"]
    assert after == before - 1

    fetched = orders.get_order_status(order["order_id"])
    assert fetched["order_id"] == order["order_id"]


def test_create_order_rejects_insufficient_stock():
    try:
        orders.create_order(
            items=[{"sku": "WARF5", "quantity": 1}],
            branch_id="zona1",
            prescription_id="RX-TEST-001",
        )
        assert False, "expected PharmacyError"
    except PharmacyError as exc:
        assert "not enough stock" in str(exc).lower()


# --- tools.py error wrapping ---------------------------------------------------


def test_tool_wraps_domain_error_as_tool_result():
    tool = get_tool("get_medication_details")
    result = tool.call({"sku": "NOPE"})
    assert result.is_error is True
    assert "unknown medication" in result.text().lower()


def test_tool_wraps_missing_argument_as_tool_result():
    tool = get_tool("check_stock")
    result = tool.call({})
    assert result.is_error is True


def test_tool_success_returns_json_text():
    tool = get_tool("search_medications")
    result = tool.call({"therapeutic_class": "antihistamine"})
    assert result.is_error is False
    payload = json.loads(result.text())
    assert any(item["sku"] == "LORA10" for item in payload)


# --- dispatcher end-to-end ------------------------------------------------------


def test_dispatcher_initialize_then_tools_list():
    dispatcher = Dispatcher()
    init_response = dispatcher.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init_response["result"]["serverInfo"]["name"] == "pharmacy-mcp"

    notif_response = dispatcher.handle(
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    )
    assert notif_response is None

    list_response = dispatcher.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tool_names = {t["name"] for t in list_response["result"]["tools"]}
    assert "assess_symptoms" in tool_names
    assert "create_order" in tool_names


def test_dispatcher_unknown_method_returns_json_rpc_error():
    dispatcher = Dispatcher()
    response = dispatcher.handle({"jsonrpc": "2.0", "id": 1, "method": "not/a/method"})
    assert response["error"]["code"] == -32601


def test_dispatcher_tools_call_success():
    dispatcher = Dispatcher()
    response = dispatcher.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "assess_symptoms", "arguments": {"symptoms": ["headache"]}},
        }
    )
    assert response["result"]["isError"] is False
