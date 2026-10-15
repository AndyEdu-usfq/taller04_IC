"""RAG de Taller 04: corpus local, Qdrant y generación exclusivamente en la H200.

Flujo: PDFs/TXT → embeddings H200 → Qdrant → recuperación → H200.chat.
No usa OpenAI, Anthropic ni API keys.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pypdf import PdfReader
from qdrant_client import QdrantClient, models

from taller04.h200 import H200


PROJECT_DIR = Path(__file__).resolve().parents[2]
CORPUS_DIR = PROJECT_DIR / "corpus"
ABSTENCION = "El corpus no contiene información suficiente."
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "taller04_kubernetes")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")


class EmbeddingChatClient(Protocol):
    def embeddings(self, textos: str | list[str]) -> list[list[float]]: ...

    def chat(self, mensajes: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Fragmento:
    """Unidad indexable con trazabilidad hasta el documento y la página."""

    id: str
    documento: str
    pagina: int | None
    texto: str


def leer_documento(path: Path) -> list[tuple[int | None, str]]:
    """Extrae texto de PDF, TXT, Markdown y JSON sin convertir formatos a ciegas."""
    if path.suffix.lower() == ".pdf":
        return [
            (number, page.extract_text() or "")
            for number, page in enumerate(PdfReader(str(path)).pages, start=1)
        ]
    return [(None, path.read_text(encoding="utf-8"))]


def fragmentar(texto: str, tamano: int = 1800, solapamiento: int = 250) -> list[str]:
    """Divide texto por caracteres conservando solapamiento para no romper contexto."""
    limpio = " ".join(texto.split())
    if not limpio:
        return []
    if tamano <= solapamiento:
        raise ValueError("tamano debe ser mayor que solapamiento")
    paso = tamano - solapamiento
    return [limpio[inicio:inicio + tamano] for inicio in range(0, len(limpio), paso)]


def cargar_corpus(corpus_dir: Path = CORPUS_DIR, tamano: int = 1800,
                  solapamiento: int = 250) -> list[Fragmento]:
    """Carga documentos soportados y devuelve fragmentos con ids deterministas."""
    extensiones = {".pdf", ".txt", ".md", ".markdown", ".json"}
    fragmentos: list[Fragmento] = []
    for path in sorted(corpus_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in extensiones:
            continue
        for pagina, texto in leer_documento(path):
            for indice, contenido in enumerate(fragmentar(texto, tamano, solapamiento)):
                pagina_id = f"-p{pagina}" if pagina is not None else ""
                fragmentos.append(Fragmento(
                    id=f"{path.stem}{pagina_id}-c{indice}",
                    documento=path.name,
                    pagina=pagina,
                    texto=contenido,
                ))
    return fragmentos


class RagTaller04:
    """Índice vectorial Qdrant y generación grounded usando únicamente la H200."""

    def __init__(self, cliente: EmbeddingChatClient | None = None,
                 corpus_dir: Path = CORPUS_DIR,
                 qdrant: QdrantClient | None = None,
                 qdrant_url: str = QDRANT_URL,
                 collection: str = QDRANT_COLLECTION):
        self.cliente = cliente or H200()
        self.corpus_dir = Path(corpus_dir)
        self.collection = collection
        self.qdrant = qdrant or QdrantClient(url=qdrant_url, api_key=QDRANT_API_KEY)
        self.fragmentos: list[Fragmento] = []

    def indexar(self, tamano: int = 1800, solapamiento: int = 250) -> int:
        """Carga el corpus y persiste sus embeddings y payloads en Qdrant."""
        self.fragmentos = cargar_corpus(self.corpus_dir, tamano, solapamiento)
        if not self.fragmentos:
            raise ValueError(f"No hay documentos indexables en {self.corpus_dir}")
        vectores = self.cliente.embeddings([fragmento.texto for fragmento in self.fragmentos])
        if len(vectores) != len(self.fragmentos):
            raise RuntimeError("La H200 devolvió un embedding por cada fragmento esperado")
        if not vectores or not vectores[0]:
            raise RuntimeError("La H200 no devolvió vectores utilizables")

        if self.qdrant.collection_exists(self.collection):
            self.qdrant.delete_collection(self.collection)
        self.qdrant.create_collection(
            collection_name=self.collection,
            vectors_config=models.VectorParams(
                size=len(vectores[0]),
                distance=models.Distance.COSINE,
            ),
        )
        points = [
            models.PointStruct(
                id=indice,
                vector=vector,
                payload={
                    "chunk_id": fragmento.id,
                    "documento": fragmento.documento,
                    "pagina": fragmento.pagina,
                    "texto": fragmento.texto,
                },
            )
            for indice, (fragmento, vector) in enumerate(zip(self.fragmentos, vectores))
        ]
        self.qdrant.upsert(collection_name=self.collection, points=points)
        return len(self.fragmentos)

    def recuperar(self, pregunta: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Consulta Qdrant y devuelve fragmentos con score y trazabilidad."""
        if not self.fragmentos:
            raise RuntimeError("Ejecuta indexar() antes de recuperar()")
        consulta = self.cliente.embeddings([pregunta])[0]
        respuesta = self.qdrant.query_points(
            collection_name=self.collection,
            query=consulta,
            limit=max(1, top_k),
            with_payload=True,
        )
        return [
            {
                "score": punto.score,
                "chunk_id": punto.payload["chunk_id"],
                "documento": punto.payload["documento"],
                "pagina": punto.payload["pagina"],
                "texto": punto.payload["texto"],
            }
            for punto in respuesta.points
        ]

    @staticmethod
    def construir_prompt(pregunta: str, contextos: list[dict[str, Any]]) -> str:
        contexto = "\n\n".join(
            f"[{indice}] {item['documento']}"
            f"{' página ' + str(item['pagina']) if item['pagina'] else ''}"
            f" / {item['chunk_id']}\n{item['texto']}"
            for indice, item in enumerate(contextos, start=1)
        )
        return (
            "Responde en español usando únicamente el contexto recuperado. "
            f"Si el contexto no contiene la respuesta, di exactamente: {ABSTENCION}\n\n"
            f"Contexto:\n{contexto}\n\nPregunta: {pregunta}\nRespuesta:"
        )

    def responder(self, pregunta: str, top_k: int = 5, max_tokens: int = 512) -> dict[str, Any]:
        """Recupera contexto y genera una respuesta grounded en la H200."""
        contextos = self.recuperar(pregunta, top_k=top_k)
        prompt = self.construir_prompt(pregunta, contextos)
        respuesta = self.cliente.chat([
            {"role": "system", "content": "Eres un experto en Kubernetes y RAG. No inventes datos."},
            {"role": "user", "content": prompt},
        ], max_tokens=max_tokens)
        return {
            "pregunta": pregunta,
            "respuesta": respuesta["contenido"],
            "contextos": contextos,
            "prompt": prompt,
            "uso": respuesta.get("uso", {}),
            "latencia_s": respuesta.get("latencia_s", 0.0),
            "modelo": getattr(self.cliente, "modelo", None),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG de Taller 03 con H200")
    parser.add_argument("pregunta", nargs="+", help="pregunta para el corpus")
    parser.add_argument("--top-k", type=int, default=5, help="fragmentos recuperados")
    args = parser.parse_args()

    rag = RagTaller04()
    total = rag.indexar()
    resultado = rag.responder(" ".join(args.pregunta), top_k=args.top_k)
    print(f"fragmentos indexados: {total}")
    print(f"modelo: {resultado['modelo']} | latencia: {resultado['latencia_s']} s")
    print(f"respuesta: {resultado['respuesta']}")
    print("\ncontextos:")
    for contexto in resultado["contextos"]:
        print(f"- {contexto['score']:.3f} {contexto['documento']} / {contexto['chunk_id']}")


if __name__ == "__main__":
    main()