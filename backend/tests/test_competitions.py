from fastapi.testclient import TestClient


def test_list_competitions(client: TestClient) -> None:
    response = client.get("/api/competitions")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert len(body["data"]) == 1
    assert body["data"][0]["name"] == "测试计算机设计大赛"


def test_get_competition_detail(client: TestClient) -> None:
    response = client.get("/api/competitions/1")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["official_verification_status"] == "官方来源已核实"
    assert body["data"]["editions"][0]["year"] == 2026
    assert body["data"]["editions"][0]["status"] == "registration_open"
    assert body["data"]["editions"][0]["official_registration_deadline"] is not None
    assert body["data"]["editions"][0]["university_registration_deadline"] is not None
    assert body["data"]["editions"][0]["freshness_status"] == "unknown"
    assert body["data"]["freshness_status"] == "unknown"
    assert body["data"]["fact_revisions"] == []
    assert body["data"]["university_notices"][0]["university_name"] == "测试大学"
    assert body["data"]["university_notices"][0]["organizing_department"] == "测试大学教务处"
    assert body["data"]["detail_ready"] is True
    assert body["data"]["history_timeline"][0]["year"] == 2020
    assert body["data"]["participation_requirements"][0]["value"] == "全日制本科生"
    assert body["data"]["competition_process"][0]["title"] == "报名"
    assert body["data"]["submission_requirements"][0]["label"] == "作品"
    assert body["data"]["award_settings"][0]["label"] == "一等奖"


def test_filter_registration_open(client: TestClient) -> None:
    response = client.get("/api/competitions?edition_status=registration_open&availability=next_90_days")

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


def test_filter_university_notice(client: TestClient) -> None:
    response = client.get("/api/competitions?source_scope=university_notice")

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert response.json()["data"][0]["university_notice_count"] == 1


def test_filter_my_university_notice(client: TestClient) -> None:
    response = client.get("/api/competitions?source_scope=my_university_notice&university_id=1")

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


def test_resolve_my_university_deadline(client: TestClient) -> None:
    response = client.get("/api/competitions/1?university_id=1")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["deadline_resolution"]["effective_deadline_type"] == "university_registration_deadline"
    assert data["deadline_resolution"]["university_name"] == "测试大学"
    assert data["effective_deadline"] == data["university_registration_deadline"]
