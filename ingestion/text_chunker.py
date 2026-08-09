import uuid
from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_documents_hierarchical(
    text_chunks: list[dict],
    report_id: str,
    parent_size: int = 512,
    parent_overlap: int = 64,
    child_size: int = 128,
    child_overlap: int = 16,
) -> tuple[list[dict], list[dict]]:
    """
    Split raw text chunks into a parent-child hierarchy.

    Parents (~512 chars) are stored in SQLite for context reconstruction.
    Children (~128 chars) are embedded and stored in Qdrant for precise matching.

    Returns:
        (parents, children) — both as lists of dicts
    """
    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=parent_size, chunk_overlap=parent_overlap
    )
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=child_size, chunk_overlap=child_overlap
    )

    parents: list[dict] = []
    children: list[dict] = []
    position = 0

    for raw in text_chunks:
        if not raw["text"].strip():
            continue

        for parent_text in parent_splitter.split_text(raw["text"]):
            if not parent_text.strip():
                continue

            parent_id = _make_id(report_id, position, parent_text)
            parents.append({
                "id": parent_id,
                "report_id": report_id,
                "text": parent_text,
                "page": raw.get("page", 0),
                "section": raw.get("section"),
                "subsection": raw.get("subsection"),
                "position": position,
            })

            for i, child_text in enumerate(child_splitter.split_text(parent_text)):
                if not child_text.strip():
                    continue
                children.append({
                    "id": _make_id(parent_id, i, child_text),
                    "parent_id": parent_id,
                    "report_id": report_id,
                    "text": child_text,
                    "page": raw.get("page", 0),
                    "section": raw.get("section"),
                    "subsection": raw.get("subsection"),
                })

            position += 1

    return parents, children


def _make_id(*parts) -> str:
    """Deterministic UUID from content — same input always produces same ID."""
    key = ":".join(str(p) for p in parts)
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, key))
