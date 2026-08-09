import re
from pathlib import Path
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import PdfFormatOption


def get_converter() -> DocumentConverter:
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options.do_cell_matching = True

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )


def parse_pdf(pdf_path: str) -> dict:
    """
    Parse a PDF and return text chunks (with section metadata) and table dataframes.

    Returns:
        {
            "text_chunks": [{"text", "page", "source", "section", "subsection"}, ...],
            "tables": [{"df", "page", "source"}, ...]
        }
    """
    converter = get_converter()
    result = converter.convert(pdf_path)
    doc = result.document

    source = str(pdf_path)
    text_chunks = []
    tables = []

    current_section = "Unknown"
    current_subsection = None

    for element, _level in doc.iterate_items():
        element_type = type(element).__name__

        if element_type == "SectionHeaderItem":
            text = element.text.strip()
            if _is_major_section(text):
                current_section = text
            current_subsection = text
            continue

        elif element_type == "TextItem":
            if not element.text.strip():
                continue
            page = element.prov[0].page_no if element.prov else 0
            text_chunks.append({
                "text": element.text,
                "page": page,
                "source": source,
                "section": current_section,
                "subsection": current_subsection,
            })

        elif element_type == "TableItem":
            try:
                page = element.prov[0].page_no if element.prov else 0
                md = element.export_to_markdown(doc=doc)
                if md and md.strip():
                    text_chunks.append({
                        "text": md,
                        "page": page,
                        "source": source,
                        "section": current_section,
                        "subsection": current_subsection,
                    })
                df = element.export_to_dataframe(doc=doc)
                tables.append({"df": df, "page": page, "source": source})
            except Exception:
                pass

    return {"text_chunks": text_chunks, "tables": tables}


def _is_major_section(text: str) -> bool:
    """
    Detect top-level structural headers using pattern matching.
    Works for any document type — no content-level assumptions.
    """
    t = text.strip().upper()
    return bool(
        re.match(r'^(PART|CHAPTER|SECTION)\s+[IVXLC\d]+', t)
        or re.match(r'^ITEM\s+\d+', t)
        or re.match(r'^NOTE\s+\d+[\.\s]', t)
    )
