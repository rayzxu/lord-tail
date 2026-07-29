from __future__ import annotations

from conftest import start_game
from app.systems.characters import armor_for_body_part


def test_character_ledger_starts_empty(client):
    state = start_game(client)
    assert state["characters"]["entries"] == []
    response = client.get("/api/characters")
    assert response.status_code == 200, response.text
    assert response.json() == {"characters": [], "total": 0}


def test_create_and_patch_non_player_character(client):
    start_game(client)
    created = client.post("/api/state/characters", json={
        "name": "玛尔塔",
        "role": "管家",
        "gender": "女",
        "age": 42,
        "faction": "北境",
        "location": "领主堡垒",
        "description_md": "城堡老管家。",
        "relationship_to_lord": "畏惧但依赖领主权威",
        "disposition": -10,
        "traits": ["管家", "识字"],
        "memories": ["第1日被领主训斥。"],
    })
    assert created.status_code == 200, created.text
    character = created.json()["character"]
    assert character["id"] == "char_1"
    assert character["name"] == "玛尔塔"
    assert created.json()["created"] is True

    patched = client.patch(f"/api/state/characters/{character['id']}", json={
        "location": "地牢门外",
        "disposition": -30,
        "memories": ["第1日被领主训斥。", "被迫为审讯作证。"],
    })
    assert patched.status_code == 200, patched.text
    updated = patched.json()["character"]
    assert updated["location"] == "地牢门外"
    assert updated["disposition"] == -30
    assert updated["memories"][-1] == "被迫为审讯作证。"

    listed = client.get("/api/characters").json()
    assert listed["total"] == 1
    assert listed["characters"][0]["id"] == "char_1"


def test_structured_character_kind_defaults_and_component_patch(client):
    start_game(client)
    created = client.post("/api/state/characters", json={
        "kind": "steward",
        "name": "玛尔塔",
        "identity": {"role": "总管", "gender": "女", "age": 42},
        "profile": {"description_md": "城堡老管家。", "traits": ["识字"]},
        "relationship": {"to_lord": "畏惧领主", "disposition": -10, "fear": 70},
        "components": {"court_official": {"access_level": 3}},
    })
    assert created.status_code == 200, created.text
    character = created.json()["character"]
    assert character["kind"] == "steward"
    assert character["role"] == "总管"
    assert character["identity"]["age"] == 42
    assert character["profile"]["traits"] == ["识字"]
    assert character["relationship"]["fear"] == 70
    assert character["components"]["court_official"]["access_level"] == 3
    assert "economy_agent" in character["components"]
    assert "health" in character["components"]

    patched = client.patch(f"/api/state/characters/{character['id']}/components/court_official", json={
        "values": {"manages": ["粮仓", "仆役"]},
    })
    assert patched.status_code == 200, patched.text
    assert patched.json()["character"]["components"]["court_official"]["manages"] == ["粮仓", "仆役"]


def test_unknown_kind_falls_back_to_commoner_and_memory_append(client):
    start_game(client)
    created = client.post("/api/state/characters", json={"kind": "witch_hunter", "name": "灰袍人", "role": "旅人", "age": 50})
    assert created.status_code == 200, created.text
    character = created.json()["character"]
    assert character["kind"] == "commoner"
    assert character["flags"]["requested_kind"] == "witch_hunter"
    assert "health" in character["components"]

    appended = client.post(f"/api/state/characters/{character['id']}/memory", json={"entry": "在城门外询问过领主的病情。"})
    assert appended.status_code == 200, appended.text
    body = appended.json()["character"]
    assert body["memories"] == ["在城门外询问过领主的病情。"]
    assert body["memory"]["entries"] == ["在城门外询问过领主的病情。"]


def test_character_ledger_rejects_lord_as_npc(client):
    start_game(client)
    response = client.post("/api/state/characters", json={"name": "Ray", "role": "领主"})
    assert response.status_code == 422
    assert "领主本人" in response.text


def test_describe_context_supports_character(client):
    start_game(client)
    created = client.post("/api/state/characters", json={
        "name": "奥托",
        "role": "商队护卫",
        "description_md": "脸上有旧刀疤的护卫。",
    }).json()["character"]
    response = client.get(f"/api/agent/describe-context?target_type=character&key={created['id']}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["target_type"] == "character"
    assert body["target"]["name"] == "奥托"
    assert body["description_rules"]["allow_state_mutation"] is False


def test_character_registry_exposes_adult_stat_enums(client):
    start_game(client)
    response = client.get("/api/characters/registry")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kinds"]["steward"]["components"] == ["court_official", "economy_agent", "health"]
    assert body["components"]["health"]["condition"] == "healthy"
    assert "missionary" in body["sex_position_ids"]
    assert body["body_content_types"]["semen"] == "精液"
    assert body["body_content_types"]["urine"] == "尿液"
    assert "poison" in body["body_content_types"]
    assert body["reproductive_content_targets"]["uterus"] == "uterine_contents"
    assert body["attribute_ids"]["STR"]["label"] == "力量"
    assert body["equipment_slots"]["right_hand"]["label"] == "右手"
    assert body["equipment_slots"]["vagina"]["adult_only"] is True
    assert "penis" in body["body_slot_presets"]["male"]["slots"]
    assert "vagina" in body["body_slot_presets"]["female"]["slots"]
    assert "penis" not in body["body_slot_presets"]["female"]["slots"]
    assert "rusty_sword" in body["items"]


def test_character_attributes_default_to_classic_six(client):
    start_game(client)
    response = client.post("/api/state/characters", json={"name": "奥托", "role": "护卫", "age": 31})
    assert response.status_code == 200, response.text
    attributes = response.json()["character"]["components"]["attributes"]
    assert attributes["base"] == {"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10}
    assert attributes["effective"] == attributes["base"]
    assert response.json()["character"]["components"]["inventory"]["items"] == []


def test_character_item_grant_equip_and_unequip_recompute_attributes(client):
    start_game(client)
    character = client.post("/api/state/characters", json={"name": "奥托", "role": "护卫", "age": 31}).json()["character"]

    granted = client.post(f"/api/state/characters/{character['id']}/items", json={"item_id": "rusty_sword", "quantity": 1})
    assert granted.status_code == 200, granted.text
    assert granted.json()["character"]["components"]["inventory"]["items"][0]["item_id"] == "rusty_sword"

    equipped = client.post(f"/api/state/characters/{character['id']}/equipment/equip", json={"item_id": "heavy_chainmail"})
    assert equipped.status_code == 200, equipped.text
    components = equipped.json()["character"]["components"]
    assert components["equipment"]["slots"]["torso"] == "heavy_chainmail"
    assert components["attributes"]["equipment_modifiers"] == {"DEX": -1, "CON": 2}
    assert components["attributes"]["effective"]["DEX"] == 9
    assert components["attributes"]["effective"]["CON"] == 12

    unequipped = client.post(f"/api/state/characters/{character['id']}/equipment/unequip", json={"slot": "torso"})
    assert unequipped.status_code == 200, unequipped.text
    assert unequipped.json()["character"]["components"]["equipment"]["slots"] == {}
    assert unequipped.json()["character"]["components"]["attributes"]["effective"]["DEX"] == 10


def test_equipped_item_can_create_realm_effects_without_mutating_base_resources(client):
    start_game(client)
    character = client.post("/api/state/characters", json={"name": "玛尔塔", "role": "管家", "age": 42}).json()["character"]
    equipped = client.post(f"/api/state/characters/{character['id']}/equipment/equip", json={"item_id": "grain_tithe_seal"})
    assert equipped.status_code == 200, equipped.text
    state = equipped.json()["state"]
    assert state["resources"]["authority"] == 50
    assert state["resources"]["food"] == 500
    assert state["item_effects"]["realm_resource_modifiers"] == {"food": 20, "authority": 5}
    assert state["effective_resources"]["authority"] == 55
    assert state["effective_resources"]["food"] == 520


def test_lord_can_hold_and_equip_items_without_entering_npc_ledger(client):
    start_game(client)
    equipped = client.post("/api/state/lord/equipment/equip", json={"item_id": "steward_ring"})
    assert equipped.status_code == 200, equipped.text
    state = equipped.json()["state"]
    assert state["characters"]["entries"] == []
    lord = equipped.json()["lord"]
    assert lord["components"]["equipment"]["slots"]["accessory_1"] == "steward_ring"
    assert lord["components"]["attributes"]["effective"]["INT"] == 11
    assert lord["components"]["attributes"]["effective"]["CHA"] == 11

    detail = client.get("/api/lord/components")
    assert detail.status_code == 200, detail.text
    assert detail.json()["lord"]["components"]["equipment"]["slots"]["accessory_1"] == "steward_ring"


def test_lord_body_profile_can_be_patched_for_equipment_slots(client):
    start_game(client)
    patched = client.patch("/api/state/lord/components/body_profile", json={"values": {"available_slots": ["head", "neck", "penis", "accessory_1"]}})
    assert patched.status_code == 200, patched.text
    slots = patched.json()["lord"]["components"]["body_profile"]["available_slots"]
    assert "penis" in slots
    equipped = client.post("/api/state/lord/equipment/equip", json={"item_id": "male_chastity_device", "slot": "penis"})
    assert equipped.status_code == 200, equipped.text
    assert equipped.json()["lord"]["components"]["equipment"]["slots"]["penis"] == "male_chastity_device"


def test_two_handed_weapon_occupies_both_hands_and_blocks_conflict(client):
    start_game(client)
    character = client.post("/api/state/characters", json={"name": "冈特", "role": "骑士", "age": 31}).json()["character"]
    equipped = client.post(f"/api/state/characters/{character['id']}/equipment/equip", json={"item_id": "greatsword", "slot": "right_hand"})
    assert equipped.status_code == 200, equipped.text
    slots = equipped.json()["character"]["components"]["equipment"]["slots"]
    assert slots["left_hand"] == "greatsword"
    assert slots["right_hand"] == "greatsword"
    source = equipped.json()["character"]["components"]["equipment"]["sources"][0]
    assert set(source["occupied_slots"]) == {"left_hand", "right_hand"}

    blocked = client.post(f"/api/state/characters/{character['id']}/equipment/equip", json={"item_id": "wooden_shield", "slot": "left_hand"})
    assert blocked.status_code == 422
    assert "占用" in blocked.text


def test_armor_for_body_part_uses_equipped_slot(client):
    start_game(client)
    character = client.post("/api/state/characters", json={"name": "冈特", "role": "骑士", "age": 31}).json()["character"]
    equipped = client.post(f"/api/state/characters/{character['id']}/equipment/equip", json={"item_id": "heavy_chainmail", "slot": "torso"})
    assert equipped.status_code == 200, equipped.text
    assert armor_for_body_part(equipped.json()["character"], "torso") == 5
    assert armor_for_body_part(equipped.json()["character"], "left_arm") == 0


def test_private_equipment_requires_adult_and_declared_body_slots(client):
    start_game(client)
    adult = client.post("/api/state/characters", json={
        "name": "艾琳",
        "role": "女仆",
        "gender": "女",
        "age": 24,
        "components": {
            "body_profile": {
                "available_slots": [
                    "head", "neck", "torso", "back", "left_arm", "right_arm", "left_hand", "right_hand",
                    "waist", "left_leg", "right_leg", "left_foot", "right_foot", "accessory_1", "accessory_2", "vagina"
                ]
            }
        },
    }).json()["character"]
    equipped = client.post(f"/api/state/characters/{adult['id']}/equipment/equip", json={"item_id": "female_chastity_belt", "slot": "waist"})
    assert equipped.status_code == 200, equipped.text
    slots = equipped.json()["character"]["components"]["equipment"]["slots"]
    assert slots["waist"] == "female_chastity_belt"
    assert slots["vagina"] == "female_chastity_belt"

    minor = client.post("/api/state/characters", json={
        "name": "小彼得",
        "role": "仆役",
        "age": 17,
        "components": {"body_profile": {"available_slots": ["waist", "vagina"]}},
    }).json()["character"]
    rejected = client.post(f"/api/state/characters/{minor['id']}/equipment/equip", json={"item_id": "female_chastity_belt", "slot": "waist"})
    assert rejected.status_code == 422
    assert "成年" in rejected.text


def test_private_equipment_dependency_uses_slot_tags(client):
    start_game(client)
    character = client.post("/api/state/characters", json={
        "name": "艾琳",
        "role": "女仆",
        "gender": "女",
        "age": 24,
        "components": {
            "body_profile": {
                "available_slots": [
                    "head", "neck", "torso", "back", "left_arm", "right_arm", "left_hand", "right_hand",
                    "waist", "left_leg", "right_leg", "left_foot", "right_foot", "accessory_1", "accessory_2",
                    "left_nipple", "right_nipple", "nipple_chain"
                ]
            }
        },
    }).json()["character"]
    blocked = client.post(f"/api/state/characters/{character['id']}/equipment/equip", json={"item_id": "nipple_chain", "slot": "nipple_chain"})
    assert blocked.status_code == 422

    assert client.post(f"/api/state/characters/{character['id']}/equipment/equip", json={"item_id": "nipple_ring", "slot": "left_nipple"}).status_code == 200
    assert client.post(f"/api/state/characters/{character['id']}/equipment/equip", json={"item_id": "nipple_ring", "slot": "right_nipple"}).status_code == 200
    equipped = client.post(f"/api/state/characters/{character['id']}/equipment/equip", json={"item_id": "nipple_chain", "slot": "nipple_chain"})
    assert equipped.status_code == 200, equipped.text
    assert equipped.json()["character"]["components"]["equipment"]["slots"]["nipple_chain"] == "nipple_chain"


def test_items_catalog_endpoint(client):
    start_game(client)
    response = client.get("/api/items")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["attribute_ids"]["CHA"]["label"] == "魅力"
    assert body["equipment_slots"]["torso"]["label"] == "躯干"
    assert "anus" in body["body_slot_presets"]["male"]["slots"]
    assert body["items"]["grain_tithe_seal"]["effects"]["realm_resources"]["authority"] == 5


def test_character_sexual_encounter_accumulates_partner_and_position_counts(client):
    start_game(client)
    first = client.post("/api/state/characters", json={"name": "艾琳", "role": "女仆", "gender": "女", "age": 24}).json()["character"]
    second = client.post("/api/state/characters", json={"name": "奥托", "role": "护卫", "gender": "男", "age": 31}).json()["character"]

    response = client.post(f"/api/state/characters/{first['id']}/sexual-encounters", json={
        "partner_character_id": second["id"],
        "position_id": "standing",
        "count": 2,
        "notes": ["测试标签"],
    })
    assert response.status_code == 200, response.text
    response = client.post(f"/api/state/characters/{first['id']}/sexual-encounters", json={
        "partner_character_id": second["id"],
        "position_id": "standing",
        "count": 1,
    })
    assert response.status_code == 200, response.text

    history = response.json()["character"]["components"]["sexual_history"]
    assert history["total_partner_count"] == 1
    assert history["total_encounter_count"] == 3
    assert history["position_totals"]["standing"] == 3
    partner = history["partners"][second["id"]]
    assert partner["encounter_count"] == 3
    assert partner["position_counts"]["standing"] == 3
    assert partner["notes"] == ["测试标签"]


def test_character_reproductive_contents_append_and_clear_expired(client):
    start_game(client)
    target = client.post("/api/state/characters", json={"name": "艾琳", "role": "女仆", "gender": "女", "age": 24}).json()["character"]
    source = client.post("/api/state/characters", json={"name": "奥托", "role": "护卫", "gender": "男", "age": 31}).json()["character"]

    for bucket, content_type in [("stomach", "wine"), ("intestine", "urine"), ("uterus", "semen")]:
        response = client.post(f"/api/state/characters/{target['id']}/reproductive-contents", json={
            "target": bucket,
            "content_type": content_type,
            "source_character_id": source["id"],
            "amount": 1,
            "expires_time": {"calendar_day": 1, "clock_24": "07:00"},
        })
        assert response.status_code == 200, response.text

    contents = response.json()["character"]["components"]["reproductive_contents"]
    assert contents["stomach_contents"][0]["content_type"] == "wine"
    assert contents["intestinal_contents"][0]["content_type"] == "urine"
    assert contents["uterine_contents"][0]["content_type"] == "semen"
    assert contents["uterine_contents"][0]["source_character_id"] == source["id"]

    clear = client.post(f"/api/state/characters/{target['id']}/reproductive-contents/clear-expired", json={
        "now": {"calendar_day": 1, "clock_24": "08:00"},
    })
    assert clear.status_code == 200, clear.text
    assert clear.json()["removed"] == {
        "stomach_contents": 1,
        "intestinal_contents": 1,
        "uterine_contents": 1,
    }


def test_character_adult_stats_reject_minor_or_unknown_age(client):
    start_game(client)
    minor = client.post("/api/state/characters", json={"name": "小彼得", "role": "仆役", "age": 17}).json()["character"]
    unknown = client.post("/api/state/characters", json={"name": "无龄者", "role": "旅人"}).json()["character"]

    minor_response = client.post(f"/api/state/characters/{minor['id']}/sexual-encounters", json={
        "partner_character_id": "player_lord",
        "position_id": "standing",
    })
    assert minor_response.status_code == 422

    unknown_response = client.post(f"/api/state/characters/{unknown['id']}/reproductive-contents", json={
        "target": "stomach",
        "content_type": "water",
        "source_character_id": "external_unknown",
    })
    assert unknown_response.status_code == 422
