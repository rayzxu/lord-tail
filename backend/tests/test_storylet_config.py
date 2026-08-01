from app.storylets.config import get_definition, load_definitions, validate_storylet_catalog


def test_storylet_catalog_is_valid_and_has_vertical_chain():
    validate_storylet_catalog()
    definitions = load_definitions()
    assert ("petition_building_credit", "petition") in definitions
    assert ("petition_building_credit", "construction_completed") in definitions
    assert ("petition_building_credit", "loan_repayment_due") in definitions
    assert len(get_definition("petition_building_credit", "petition")["choices"]) == 6
