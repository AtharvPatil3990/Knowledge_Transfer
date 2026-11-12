from dataclasses import dataclass

from app.services.llm_orchestrator import embeddings_model

@dataclass(frozen=True)
class TextChunk:
    index: int
    content: str


def chunk_text(content: str, size: int = 1200, overlap: int = 150) -> list[TextChunk]:
    if size <= overlap:
        raise ValueError("Chunk size must be greater than overlap.")
    normalized = " ".join(content.split())
    if not normalized:
        return []

    chunks = []
    start = 0
    index = 0
    while start < len(normalized):
        end = min(start + size, len(normalized))
        chunks.append(TextChunk(index=index, content=normalized[start:end]))
        if end == len(normalized):
            break
        start = end - overlap
        index += 1
    return chunks


class EmbeddingService:
    model = "BAAI/bge-small-en-v1.5"

    def embed(self, chunks: list[TextChunk]) -> list[list[float]]:
        if not chunks:
            return []
        return embeddings_model.embed_documents([chunk.content for chunk in chunks])
