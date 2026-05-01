import pytest

from pur_leads.integrations.documents.pdf_parser import PdfArtifactParser


@pytest.mark.asyncio
async def test_pdf_artifact_parser_returns_non_empty_page_chunks(tmp_path):
    pdf_path = tmp_path / "catalog.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    parser = PdfArtifactParser(
        reader_factory=lambda path: FakeReader(
            [
                FakePage(" Dahua Hero A1 \n\n Wi-Fi camera "),
                FakePage("   "),
                FakePage("Relay module\nDIN rail"),
            ]
        ),
        parser_version="test-version",
    )

    parsed = await parser.parse_artifact(
        source_id="source-1",
        artifact_id="artifact-1",
        payload={"local_path": str(pdf_path)},
    )

    assert parsed.source_id == "source-1"
    assert parsed.artifact_id == "artifact-1"
    assert parsed.parser_name == "pypdf"
    assert parsed.parser_version == "test-version"
    assert parsed.chunks == [
        "Dahua Hero A1\nWi-Fi camera",
        "Relay module\nDIN rail",
    ]


@pytest.mark.asyncio
async def test_pdf_artifact_parser_requires_local_path():
    parser = PdfArtifactParser(reader_factory=lambda path: FakeReader([]))

    with pytest.raises(ValueError, match="payload.local_path"):
        await parser.parse_artifact(
            source_id="source-1",
            artifact_id="artifact-1",
            payload={},
        )


@pytest.mark.asyncio
async def test_document_parser_returns_chunks_for_text_documents(tmp_path):
    text_path = tmp_path / "catalog.txt"
    text_path.write_text(
        "Dahua Hero A1 камера\n\n"
        "Умные реле, датчики протечки и настройка Home Assistant",
        encoding="utf-8",
    )
    parser = PdfArtifactParser(reader_factory=lambda path: FakeReader([]))

    parsed = await parser.parse_artifact(
        source_id="source-1",
        artifact_id="artifact-1",
        payload={
            "local_path": str(text_path),
            "file_name": "catalog.txt",
            "mime_type": "text/plain",
        },
    )

    assert parsed.parser_name == "plain-text"
    assert parsed.chunks == [
        "Dahua Hero A1 камера\n\nУмные реле, датчики протечки и настройка Home Assistant"
    ]


class FakeReader:
    def __init__(self, pages):
        self.pages = pages


class FakePage:
    def __init__(self, text):
        self.text = text

    def extract_text(self):
        return self.text
