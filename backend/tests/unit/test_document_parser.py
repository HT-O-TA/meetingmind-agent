from app.services.document_parser import DocumentParser


def test_parse_text_decodes_common_encoding():
    parser = DocumentParser()

    parsed = parser.parse("项目会议记录".encode("utf-8"), "txt")

    assert parsed.content == "项目会议记录"
    assert parsed.metadata["parser"] == "txt"


def test_parse_csv_table_to_markdown():
    parser = DocumentParser()

    parsed = parser.parse("姓名,任务\n张三,整理纪要\n李四,跟进风险\n".encode("utf-8"), "csv")

    assert "| 姓名 | 任务 |" in parsed.content
    assert "| 张三 | 整理纪要 |" in parsed.content
    assert parsed.metadata["tables"] == 1


def test_parse_legacy_doc_returns_warning_without_content():
    parser = DocumentParser()

    parsed = parser.parse(b"legacy-doc-binary", "doc")

    assert parsed.content == ""
    assert parsed.metadata["parser"] == "unsupported"
    assert ".doc" in parsed.metadata["warning"]
