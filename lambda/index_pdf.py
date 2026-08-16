"""
index_pdf.py
==============

Script d'indexation des documents internes (PDF) dans la base de
connaissances (OpenSearch). À exécuter manuellement (hors Lambda, par ex.
`python index_pdf.py`) à chaque ajout/mise à jour de documents dans
`documents/`.

Chaque PDF est :
  1. extrait en texte brut,
  2. découpé en chunks (avec un léger recouvrement pour ne pas couper une
     idée en plein milieu),
  3. embeddé (Titan) puis indexé dans OpenSearch sous la session technique
     `knowledge_base` — c'est cette même session que `tools/search.py`
     interroge via l'outil `recherche_documentaire`.
"""

import os

from langchain_text_splitters import RecursiveCharacterTextSplitter
from PyPDF2 import PdfReader

from services.bedrock_service import invoke_titan_embedding
from utils import generate_timestamp
from vector_store import vector_store

KNOWLEDGE_BASE_SESSION_ID = "knowledge_base"


def index_pdfs_in_directory(directory: str) -> None:
    """Indexe tous les PDFs d'un dossier dans OpenSearch."""

    for filename in os.listdir(directory):
        if not filename.endswith(".pdf"):
            continue

        pdf_path = os.path.join(directory, filename)
        print(f"📄 Indexation de {filename}...")

        # Extraire le texte de toutes les pages.
        reader = PdfReader(pdf_path)
        text = "".join(page.extract_text() or "" for page in reader.pages)

        # Découper en chunks avec chevauchement, pour garder du contexte
        # de part et d'autre de chaque coupure.
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", ".", " ", ""],
        )
        chunks = text_splitter.split_text(text)

        for i, chunk in enumerate(chunks):
            if len(chunk.strip()) < 10:
                continue  # on ignore les chunks trop courts (bruit)

            embedding = invoke_titan_embedding(chunk)
            vector_store.save_document(
                session_id=KNOWLEDGE_BASE_SESSION_ID,
                role="document",
                content=chunk,
                timestamp=generate_timestamp(),
                embedding=embedding,
            )

            if i % 10 == 0:
                print(f"   {i + 1}/{len(chunks)} chunks indexés")

        print(f"✅ {filename} indexé ({len(chunks)} chunks)")


if __name__ == "__main__":
    index_pdfs_in_directory("documents/")
