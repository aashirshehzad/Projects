"""
RAG Pipeline for Legal Documents
=================================
Read PDFs → Chunk text → Embed → Store in ChromaDB → Retrieve → Answer with Ollama

Fully local stack — no API credits required.
Dependencies: chromadb, sentence-transformers, pypdf, ollama, langchain
LLM backend: Ollama running llama3 or phi3
"""

import os
import sys
import textwrap
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import ollama


# ─── Configuration ───────────────────────────────────────────────────
DOCS_DIR = os.path.join(os.path.dirname(__file__), "documents")
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION_NAME = "legal_documents"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"        # fast, good quality, runs locally
LLM_MODEL = "llama3"                         # change to "phi3" if preferred

# Chunking parameters
CHUNK_SIZE = 500          # characters per chunk
CHUNK_OVERLAP = 100       # overlap to preserve context across chunks

# Retrieval parameters
TOP_K = 5                 # number of chunks to retrieve


# ─── Step 1: Load PDFs ──────────────────────────────────────────────
def load_pdfs(docs_dir: str) -> list[dict]:
    """Load all PDFs from a directory and return a list of
    {text, source, page} dicts."""
    documents = []
    pdf_files = [f for f in os.listdir(docs_dir) if f.lower().endswith(".pdf")]

    if not pdf_files:
        print(f"[ERROR] No PDF files found in {docs_dir}")
        sys.exit(1)

    for filename in sorted(pdf_files):
        filepath = os.path.join(docs_dir, filename)
        print(f"  [LOAD] Loading: {filename}")
        loader = PyPDFLoader(filepath)
        pages = loader.load()
        for page in pages:
            documents.append({
                "text": page.page_content,
                "source": filename,
                "page": page.metadata.get("page", 0),
            })
    print(f"  -> Loaded {len(documents)} pages from {len(pdf_files)} PDFs\n")
    return documents


# ─── Step 2: Chunk Text ─────────────────────────────────────────────
def chunk_documents(documents: list[dict]) -> list[dict]:
    """Split documents into smaller, overlapping chunks for better
    retrieval granularity."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = []
    for doc in documents:
        splits = splitter.split_text(doc["text"])
        for i, split in enumerate(splits):
            chunks.append({
                "text": split,
                "source": doc["source"],
                "page": doc["page"],
                "chunk_index": i,
            })

    print(f"  [CHUNK] Created {len(chunks)} chunks "
          f"(size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})\n")
    return chunks


# ─── Step 3: Create Embeddings & Store in ChromaDB ───────────────────
def build_vector_store(chunks: list[dict]) -> chromadb.Collection:
    """Embed chunks using sentence-transformers and store them in
    a persistent ChromaDB collection."""
    print(f"  [EMBED] Embedding model: {EMBEDDING_MODEL}")

    embedding_fn = SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL,
    )

    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # Delete existing collection to rebuild from scratch
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    # Prepare batch data
    ids = []
    texts = []
    metadatas = []
    for i, chunk in enumerate(chunks):
        ids.append(f"chunk_{i}")
        texts.append(chunk["text"])
        metadatas.append({
            "source": chunk["source"],
            "page": chunk["page"],
            "chunk_index": chunk["chunk_index"],
        })

    # Add in batches (ChromaDB handles embeddings internally)
    BATCH = 100
    for start in range(0, len(ids), BATCH):
        end = min(start + BATCH, len(ids))
        collection.add(
            ids=ids[start:end],
            documents=texts[start:end],
            metadatas=metadatas[start:end],
        )

    print(f"  [STORE] Stored {collection.count()} chunks in ChromaDB at {CHROMA_DIR}\n")
    return collection


# ─── Step 4: Retrieve Relevant Chunks ───────────────────────────────
def retrieve(collection: chromadb.Collection, query: str,
             top_k: int = TOP_K) -> list[dict]:
    """Query the vector store and return the top-k most relevant chunks."""
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    retrieved = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        retrieved.append({
            "text": doc,
            "source": meta["source"],
            "page": meta["page"],
            "distance": round(dist, 4),
        })
    return retrieved


# ─── Step 5: Generate Answer with Ollama ─────────────────────────────
SYSTEM_PROMPT = textwrap.dedent("""\
    You are a helpful legal document assistant. Your job is to answer
    questions ONLY using the provided context from company documents.

    STRICT RULES:
    1. Answer ONLY based on the context provided below.
    2. If the context does not contain enough information to answer the
       question, say: "I cannot find this information in the provided
       documents."
    3. Do NOT make up, infer, or hallucinate information that is not
       explicitly stated in the context.
    4. Always cite which document the information comes from.
    5. Be concise and direct.
""")


def generate_answer(query: str, context_chunks: list[dict]) -> str:
    """Send the query + retrieved context to Ollama and return the answer."""
    # Build context string with source attribution
    context_parts = []
    for i, chunk in enumerate(context_chunks, 1):
        source = chunk["source"].replace("_", " ").replace(".pdf", "")
        context_parts.append(
            f"[Source {i}: {source}, Page {chunk['page'] + 1}]\n{chunk['text']}"
        )
    context_str = "\n\n---\n\n".join(context_parts)

    user_message = (
        f"CONTEXT FROM COMPANY DOCUMENTS:\n\n{context_str}\n\n"
        f"---\n\nQUESTION: {query}\n\n"
        f"Answer the question using ONLY the context above. "
        f"Cite the source document(s)."
    )

    response = ollama.chat(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        options={"temperature": 0.1},  # low temperature for factual answers
    )

    return response["message"]["content"]


# ─── Main Pipeline ───────────────────────────────────────────────────
def build_index() -> chromadb.Collection:
    """Run the full indexing pipeline: load → chunk → embed → store."""
    print("=" * 60)
    print("  RAG PIPELINE — INDEXING PHASE")
    print("=" * 60)

    print("\n[1] Step 1: Loading PDFs...")
    documents = load_pdfs(DOCS_DIR)

    print("[2] Step 2: Chunking documents...")
    chunks = chunk_documents(documents)

    print("[3] Step 3: Embedding & storing in ChromaDB...")
    collection = build_vector_store(chunks)

    print("[DONE] Indexing complete!\n")
    return collection


def ask(query: str, collection: chromadb.Collection) -> str:
    """Run the full query pipeline: retrieve → generate."""
    print(f"\n{'-' * 60}")
    print(f"[Q] Question: {query}")
    print(f"{'-' * 60}")

    # Retrieve
    print(f"\n[SEARCH] Retrieving top-{TOP_K} relevant chunks...")
    chunks = retrieve(collection, query)

    print("\n[RESULTS] Retrieved chunks:")
    for i, chunk in enumerate(chunks, 1):
        source = chunk["source"].replace("_", " ").replace(".pdf", "")
        print(f"  [{i}] {source} (page {chunk['page']+1}) "
              f"— distance: {chunk['distance']}")
        # Show a preview of the chunk
        preview = chunk["text"][:120].replace("\n", " ")
        print(f"      \"{preview}...\"")

    # Generate
    print(f"\n[LLM] Generating answer with {LLM_MODEL}...")
    answer = generate_answer(query, chunks)

    print(f"\n[ANSWER]\n")
    # Wrap for readability
    for line in answer.split("\n"):
        print(textwrap.fill(line, width=78, initial_indent="  ",
                            subsequent_indent="  "))

    return answer


# ─── Interactive Mode ────────────────────────────────────────────────
def interactive_mode(collection: chromadb.Collection):
    """Run an interactive Q&A loop."""
    print("\n" + "=" * 60)
    print("  RAG PIPELINE — INTERACTIVE Q&A")
    print("  Type your question and press Enter.")
    print("  Type 'quit' or 'exit' to stop.")
    print("=" * 60)

    # Sample questions to try
    print("\nSample questions you can ask:")
    print("  - What is the notice period?")
    print("  - Can annual leave be carried over?")
    print("  - How many days of remote work are allowed?")
    print("  - What is the redundancy pay entitlement?")
    print("  - What happens during the probation period?")
    print("  - What are the IT security requirements?")
    print("  - What is the disciplinary process?")

    while True:
        print()
        try:
            query = input(">> Your question: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            print("\nGoodbye!")
            break

        ask(query, collection)


# ─── Entry Point ─────────────────────────────────────────────────────
if __name__ == "__main__":
    # Build index
    collection = build_index()

    # If a question was passed as CLI argument, answer it and exit
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        ask(query, collection)
    else:
        # Interactive mode
        interactive_mode(collection)
