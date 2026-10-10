from pathlib import Path

from app.services.policy_list_extractor import analyze_policy_content, extract_policy_entries, parse_policy_file


def names(entries):
    return [entry["raw_competition_name"] for entry in entries]


def test_html_table_and_list_keep_each_name_and_location():
    html = """<table><tr><th>序号</th><th>竞赛名称</th><th>类别</th></tr>
    <tr><td>1</td><td>全国大学生数学建模竞赛</td><td>A类</td></tr>
    <tr><td>2</td><td>中国大学生计算机设计大赛</td><td>B类</td></tr></table>
    <ul><li>蓝桥杯全国软件和信息技术专业人才大赛</li></ul>"""
    entries = extract_policy_entries(html, format="html")
    assert names(entries) == ["全国大学生数学建模竞赛", "中国大学生计算机设计大赛", "蓝桥杯全国软件和信息技术专业人才大赛"]
    assert all(entry["evidence_text"] and entry["locator"] for entry in entries)


def test_numbered_lines_and_delimited_clause_exclude_negation_and_prose():
    content = """一、认定范围
1. 全国大学生数学建模竞赛（A类）
2. 中国大学生计算机设计大赛（B类）
不予认定蓝桥杯全国软件和信息技术专业人才大赛。
认定竞赛包括：全国大学生电子设计竞赛、全国大学生机械创新设计大赛。
请各学院于周五前提交材料。"""
    entries = extract_policy_entries(content)
    assert names(entries) == ["全国大学生数学建模竞赛", "中国大学生计算机设计大赛", "全国大学生电子设计竞赛", "全国大学生机械创新设计大赛"]
    assert entries[0]["locator"] == "line:2"


def test_pdf_wrapped_table_name_is_kept_once():
    content = "竞赛名称\t类别\n1\t全国大学生\n数学建模竞赛\tA类\n2\t中国大学生计算机设计大赛\tB类"
    entries = extract_policy_entries(content, format="pdf")
    assert names(entries) == ["全国大学生数学建模竞赛", "中国大学生计算机设计大赛"]
    assert "全国大学生\n数学建模竞赛" in entries[0]["evidence_text"]
    assert entries[0]["locator"] == "line:2"


def test_pdf_wrap_keeps_child_track_suffix_in_name():
    content = "序号\t竞赛名称\t类别\n1\t挑战杯全国大学生课外学术科技作品竞赛\n人工智能专项赛\tA类"
    assert names(extract_policy_entries(content, format="pdf")) == ["挑战杯全国大学生课外学术科技作品竞赛人工智能专项赛"]


def test_pdf_class_prefix_rows_are_list_entries():
    content = "A类 全国大学生数学建模竞赛\nB类 中国大学生计算机设计大赛\n备注：请各学院提交材料"
    assert names(extract_policy_entries(content, format="pdf")) == ["全国大学生数学建模竞赛", "中国大学生计算机设计大赛"]


def test_tabular_rows_without_header_find_the_only_competition_cell():
    content = "A类\t全国大学生数学建模竞赛\t理学院\nB类\t中国大学生计算机设计大赛\t计算机学院"
    assert names(extract_policy_entries(content)) == ["全国大学生数学建模竞赛", "中国大学生计算机设计大赛"]


def test_named_table_column_keeps_event_titles_without_competition_keyword_and_material_name():
    content = "竞赛名称\t认定类别\n1.0\t全国大学生创新年会\tA类\n2.0\t全国大学生混凝土材料设计大赛\tC类"
    result = analyze_policy_content(content)
    assert names(result["entries"]) == ["全国大学生创新年会", "全国大学生混凝土材料设计大赛"]
    assert result["extraction_complete"] is True


def test_html_nested_paragraph_in_table_cell_keeps_name():
    html = "<table><tr><th>竞赛名称</th></tr><tr><td><p>全国大学生数学建模竞赛</p></td></tr></table>"
    assert names(extract_policy_entries(html, format="html")) == ["全国大学生数学建模竞赛"]


def test_excluded_text_section_stays_excluded_until_explicit_recognition_heading():
    content = """一、不予认定的赛事
1. 全国大学生数学建模竞赛
2. 中国大学生计算机设计大赛
二、赛事说明
3. 蓝桥杯全国软件和信息技术专业人才大赛
三、学校认定竞赛目录
1. 全国大学生电子设计竞赛"""
    assert names(extract_policy_entries(content)) == ["全国大学生电子设计竞赛"]


def test_unnumbered_inclusion_heading_resets_excluded_section():
    content = "不予认定的赛事\n1. 全国大学生数学建模竞赛\n学校认定赛事目录\n1. 全国大学生电子设计竞赛"
    assert names(extract_policy_entries(content)) == ["全国大学生电子设计竞赛"]


def test_following_rows_under_exclusion_paragraph_are_not_extracted():
    content = """以下竞赛不纳入推免加分范围：
1. 全国大学生数学建模竞赛
2. 中国大学生计算机设计大赛
以下竞赛纳入推免加分范围：
1. 全国大学生电子设计竞赛"""
    entries = extract_policy_entries(content)
    assert names(entries) == ["全国大学生电子设计竞赛"]
    assert entries[0]["section_heading"] == "以下竞赛纳入推免加分范围："


def test_html_paragraph_exclusion_applies_to_following_list():
    html = """<p>以下竞赛不纳入推免加分范围：</p>
    <ol><li>全国大学生数学建模竞赛</li></ol>
    <p>以下竞赛纳入推免加分范围：</p>
    <ol><li>全国大学生电子设计竞赛</li></ol>"""
    assert names(extract_policy_entries(html, format="html")) == ["全国大学生电子设计竞赛"]


def test_html_reference_heading_excludes_following_table_and_list():
    html = """<h2>附件二：仅供参考的赛事名单</h2>
    <table><tr><th>竞赛名称</th></tr><tr><td>全国大学生数学建模竞赛</td></tr></table>
    <ul><li>中国大学生计算机设计大赛</li></ul>
    <h2>附件三：学校认定赛事目录</h2>
    <table><tr><th>竞赛名称</th></tr><tr><td>全国大学生电子设计竞赛</td></tr></table>"""
    assert names(extract_policy_entries(html, format="html")) == ["全国大学生电子设计竞赛"]


def test_table_status_column_excludes_unrecognized_and_reference_rows():
    content = """竞赛名称\t是否认定\n全国大学生数学建模竞赛\t是
中国大学生计算机设计大赛\t否
蓝桥杯全国软件和信息技术专业人才大赛\t仅供参考"""
    assert names(extract_policy_entries(content)) == ["全国大学生数学建模竞赛"]


def test_table_header_scope_does_not_leak_into_next_table():
    html = """<table><tr><th>认定状态</th><th>竞赛名称</th></tr>
    <tr><td>是</td><td>全国大学生数学建模竞赛</td></tr></table>
    <table><tr><td>全国大学生电子设计竞赛</td><td>A类</td></tr></table>"""
    assert names(extract_policy_entries(html, format="html")) == ["全国大学生数学建模竞赛", "全国大学生电子设计竞赛"]


def test_text_benefit_headings_are_preserved_on_each_entry():
    content = """一、奖金奖励赛事
1. 全国大学生数学建模竞赛
二、推免加分赛事
1. 全国大学生电子设计竞赛"""
    entries = extract_policy_entries(content)
    assert names(entries) == ["全国大学生数学建模竞赛", "全国大学生电子设计竞赛"]
    assert [entry["section_heading"] for entry in entries] == ["一、奖金奖励赛事", "二、推免加分赛事"]


def test_html_benefit_heading_and_table_column_are_preserved():
    html = """<h2>推免加分赛事</h2><table><tr><th>竞赛名称</th><th>认定用途</th></tr>
    <tr><td>全国大学生数学建模竞赛</td><td>推免加分</td></tr></table>"""
    entry = extract_policy_entries(html, format="html")[0]
    assert entry["section_heading"] == "推免加分赛事"
    assert entry["benefit_context"] == {"认定用途": "推免加分"}


def test_merged_table_section_rows_control_following_names():
    html = """<table><tr><th>竞赛名称</th></tr>
    <tr><td colspan='2'>不予认定赛事</td></tr>
    <tr><td>全国大学生数学建模竞赛</td></tr>
    <tr><td colspan='2'>认定赛事目录</td></tr>
    <tr><td>全国大学生电子设计竞赛</td></tr></table>"""
    entries = extract_policy_entries(html, format="html")
    assert names(entries) == ["全国大学生电子设计竞赛"]
    assert entries[0]["section_heading"] == "认定赛事目录"


def test_file_adapter_marks_empty_extraction_as_incomplete(tmp_path: Path):
    path = tmp_path / "policy.txt"
    path.write_text("一、竞赛认定目录\n表格内容无法识别", encoding="utf-8")
    result = parse_policy_file(path)
    assert result["entries"] == []
    assert result["extraction_complete"] is False
    assert "no_entries" in result["extraction_warnings"]


def test_file_adapter_flags_unparsed_competition_row_even_if_other_rows_parse(tmp_path: Path):
    path = tmp_path / "policy.txt"
    path.write_text("一、认定竞赛目录\n1. 全国大学生数学建模竞赛\n① 中国大学生计算机设计大赛", encoding="utf-8")
    result = parse_policy_file(path)
    assert names(result["entries"]) == ["全国大学生数学建模竞赛"]
    assert result["extraction_complete"] is False
    assert "unparsed_competition_line:3" in result["extraction_warnings"]


def test_file_adapter_flags_ambiguous_multi_name_table_row(tmp_path: Path):
    path = tmp_path / "policy.txt"
    path.write_text("1. 全国大学生数学建模竞赛\n全国大学生电子设计竞赛\t中国大学生计算机设计大赛", encoding="utf-8")
    result = parse_policy_file(path)
    assert names(result["entries"]) == ["全国大学生数学建模竞赛"]
    assert result["extraction_complete"] is False
    assert "unparsed_competition_line:2" in result["extraction_warnings"]


def _make_ruled_pdf(path: Path, sections: list[tuple[str, str]], footers: list[str] | None = None) -> None:
    import fitz

    document = fitz.open()
    for page_number, (heading, name) in enumerate(sections):
        page = document.new_page(width=600, height=260)
        page.insert_text((50, 48), heading, fontname="china-s", fontsize=12)
        for y in (70, 100, 180):
            page.draw_line((50, y), (550, y))
        for x in (50, 420, 550):
            page.draw_line((x, 70), (x, 180))
        page.insert_text((60, 89), "竞赛名称", fontname="china-s", fontsize=11)
        page.insert_text((430, 89), "认定类别", fontname="china-s", fontsize=11)
        first, second = name.split("\n")
        page.insert_text((60, 125), first, fontname="china-s", fontsize=11)
        page.insert_text((60, 145), second, fontname="china-s", fontsize=11)
        page.insert_text((430, 125), "A类", fontname="china-s", fontsize=11)
        if footers:
            page.insert_text((50, 215), footers[page_number], fontname="china-s", fontsize=11)
    document.save(path)
    document.close()


def test_pdf_table_layer_recovers_wrapped_name_with_page_locator(tmp_path: Path):
    path = tmp_path / "policy.pdf"
    _make_ruled_pdf(path, [("一、认定竞赛目录", "全国大学生\n混凝土材料设计大赛")])
    result = parse_policy_file(path)
    assert names(result["entries"]) == ["全国大学生混凝土材料设计大赛"]
    assert result["entries"][0]["locator"].startswith("page:1/")
    assert result["extraction_complete"] is True


def test_pdf_table_layer_keeps_excluded_page_out_of_entries(tmp_path: Path):
    path = tmp_path / "policy.pdf"
    _make_ruled_pdf(path, [
        ("以下竞赛不纳入推免加分范围：", "全国大学生\n数学建模竞赛"),
        ("以下竞赛纳入推免加分范围：", "全国大学生\n电子设计竞赛"),
    ])
    result = parse_policy_file(path)
    assert names(result["entries"]) == ["全国大学生电子设计竞赛"]


def test_pdf_table_layer_does_not_treat_non_table_clause_as_catalog_row(tmp_path: Path):
    path = tmp_path / "policy.pdf"
    _make_ruled_pdf(path, [("一、认定竞赛目录", "全国大学生\n数学建模竞赛")],
                    footers=["竞赛包括：全国大学生电子设计竞赛"])
    result = parse_policy_file(path)
    assert names(result["entries"]) == ["全国大学生数学建模竞赛"]
    assert "pdf_non_table_candidates_ignored" in result["extraction_warnings"]


def test_pdf_table_without_name_column_does_not_emit_chapter_heading(tmp_path: Path):
    import fitz

    path = tmp_path / "rules.pdf"
    document = fitz.open()
    page = document.new_page(width=600, height=240)
    for y in (70, 105, 145):
        page.draw_line((50, y), (550, y))
    for x in (50, 300, 550):
        page.draw_line((x, 70), (x, 145))
    for x, y, text in ((60, 91, "章节"), (310, 91, "内容"),
                       (60, 130, "第三章"), (310, 130, "竞赛奖励")):
        page.insert_text((x, y), text, fontname="china-s", fontsize=11)
    document.save(path)
    document.close()
    result = parse_policy_file(path)
    assert result["entries"] == []
    assert result["extraction_complete"] is False


def test_file_adapter_reports_empty_pdf_as_ocr_needed(monkeypatch, tmp_path: Path):
    from app.crawler.parsers.pdf_parser import ParsedDocument, PdfParser

    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(PdfParser, "parse", lambda self, path: ParsedDocument("", "pymupdf", needs_ocr=True))
    result = parse_policy_file(path)
    assert result["entries"] == []
    assert result["needs_ocr"] is True
    assert result["parser_type"] == "pymupdf"


def test_file_adapter_reuses_document_and_legacy_parsers(monkeypatch, tmp_path: Path):
    from app.crawler.parsers.pdf_parser import ParsedDocument
    from app.crawler.parsers.docx_parser import DocxParser
    from app.crawler.parsers.excel_parser import ExcelParser
    from app.crawler.parsers.legacy_office_parser import LegacyExcelParser, LegacyWordParser

    content = "序号\t竞赛名称\t类别\n1\t全国大学生数学建模竞赛\tA类"
    for extension, parser in [("docx", DocxParser), ("xlsx", ExcelParser), ("doc", LegacyWordParser), ("xls", LegacyExcelParser)]:
        path = tmp_path / f"policy.{extension}"
        path.write_bytes(b"fixture")
        monkeypatch.setattr(parser, "parse", lambda self, path: ParsedDocument(content, "fixture"))
        result = parse_policy_file(path)
        assert names(result["entries"]) == ["全国大学生数学建模竞赛"]
        assert result["error"] is None


def test_unsupported_and_missing_files_fail_explicitly(tmp_path: Path):
    unsupported = tmp_path / "policy.bin"
    unsupported.write_bytes(b"fixture")
    assert parse_policy_file(unsupported)["error"]
    assert parse_policy_file(tmp_path / "missing.pdf")["error"]
