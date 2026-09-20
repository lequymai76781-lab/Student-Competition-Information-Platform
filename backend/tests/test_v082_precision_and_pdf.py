from tests.test_v082_discovery_helpers import make_service


def test_student_competition_notice_requires_positive_signal() -> None:
    service = make_service()
    assert service._student_competition_notice("关于开展大学生创新班遴选的通知") is False
    assert service._student_competition_notice("关于举办全国大学生计算机设计大赛的通知") is True


def test_pdf_title_prefers_competition_heading() -> None:
    service = make_service()
    text = "附件一\n关于举办全国大学生智能建造创新大赛的通知\n报名安排"
    assert service._pdf_title(text, "附件下载") == "关于举办全国大学生智能建造创新大赛的通知"
