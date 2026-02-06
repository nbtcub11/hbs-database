"""Embedding generation and FAISS index management for semantic search."""

import json
import os
from pathlib import Path
from typing import Optional

import numpy as np
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Storage paths
DATA_DIR = Path(__file__).parent / "data"
INDEX_PATH = DATA_DIR / "faiss.index"
ID_MAPPING_PATH = DATA_DIR / "id_mapping.json"
EMBEDDINGS_PATH = DATA_DIR / "embeddings.npy"

# Embedding dimensions
VOYAGE_DIMENSIONS = 1024
OPENAI_DIMENSIONS = 1536  # text-embedding-3-small default

# API keys
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Global state for loaded index
_faiss_index = None
_id_mapping = None
_embedding_provider = None  # Track which provider is being used


def is_available() -> bool:
    """Check if embeddings are configured properly (API keys available)."""
    return bool(VOYAGE_API_KEY or OPENAI_API_KEY)


def _get_voyage_embedding(text: str) -> Optional[np.ndarray]:
    """Generate embedding using Voyage AI."""
    if not VOYAGE_API_KEY:
        return None

    try:
        import voyageai

        client = voyageai.Client(api_key=VOYAGE_API_KEY)
        result = client.embed([text], model="voyage-3")
        embedding = np.array(result.embeddings[0], dtype=np.float32)
        return embedding
    except ImportError:
        print("voyageai package not installed. Install with: pip install voyageai")
        return None
    except Exception as e:
        print(f"Voyage AI embedding error: {e}")
        return None


def _get_openai_embedding(text: str) -> Optional[np.ndarray]:
    """Generate embedding using OpenAI."""
    if not OPENAI_API_KEY:
        return None

    try:
        import openai

        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
            dimensions=VOYAGE_DIMENSIONS  # Match Voyage dimensions for consistency
        )
        embedding = np.array(response.data[0].embedding, dtype=np.float32)
        return embedding
    except ImportError:
        print("openai package not installed. Install with: pip install openai")
        return None
    except Exception as e:
        print(f"OpenAI embedding error: {e}")
        return None


def generate_embedding(text: str) -> np.ndarray:
    """
    Generate embedding for text using Voyage AI, falling back to OpenAI.

    Args:
        text: The text to generate embedding for.

    Returns:
        numpy array of shape (1024,) containing the embedding.
        Returns zero vector if no API is available.
    """
    global _embedding_provider

    if not text or not text.strip():
        return np.zeros(VOYAGE_DIMENSIONS, dtype=np.float32)

    # Clean and truncate text
    text = text.strip()
    # Limit text length to avoid API limits (roughly 8000 tokens)
    if len(text) > 32000:
        text = text[:32000]

    # Try Voyage AI first
    embedding = _get_voyage_embedding(text)
    if embedding is not None:
        _embedding_provider = "voyage"
        return embedding

    # Fall back to OpenAI
    embedding = _get_openai_embedding(text)
    if embedding is not None:
        _embedding_provider = "openai"
        return embedding

    # No API available, return zero vector
    print("Warning: No embedding API available. Returning zero vector.")
    return np.zeros(VOYAGE_DIMENSIONS, dtype=np.float32)


def _create_searchable_text(person: dict) -> str:
    """Create searchable text from person data."""
    parts = []

    # Name is most important
    if person.get('name'):
        parts.append(person['name'])

    # Title provides role context
    if person.get('title'):
        parts.append(person['title'])

    # Bio provides detailed context
    if person.get('bio'):
        parts.append(person['bio'])

    # Unit/department
    if person.get('unit'):
        parts.append(f"Unit: {person['unit']}")

    # Organization
    if person.get('organization'):
        parts.append(f"Organization: {person['organization']}")

    # Tags - can be in different formats
    tags = person.get('tags', [])
    if tags:
        if isinstance(tags, list):
            if tags and isinstance(tags[0], dict):
                tag_names = [t.get('name', '') for t in tags if t.get('name')]
            else:
                tag_names = [str(t) for t in tags]
        elif isinstance(tags, str):
            tag_names = [t.strip() for t in tags.split(',')]
        else:
            tag_names = []

        if tag_names:
            parts.append(f"Tags: {', '.join(tag_names)}")

    # Also check for tag_names field (from database query)
    if person.get('tag_names'):
        parts.append(f"Tags: {person['tag_names']}")

    return " ".join(parts)


def build_index(people_data: list) -> None:
    """
    Build FAISS index from people data.

    Args:
        people_data: List of person dictionaries with id, name, title, bio, unit, tags.
    """
    global _faiss_index, _id_mapping

    if not people_data:
        print("No people data provided. Skipping index build.")
        return

    try:
        import faiss
    except ImportError:
        print("faiss package not installed. Install with: pip install faiss-cpu")
        return

    if not is_available():
        print("No embedding API configured. Cannot build index.")
        return

    print(f"Building embeddings for {len(people_data)} people...")

    embeddings = []
    id_mapping = []

    for i, person in enumerate(people_data):
        person_id = person.get('id')
        if person_id is None:
            print(f"Warning: Person at index {i} has no ID, skipping.")
            continue

        # Create searchable text
        text = _create_searchable_text(person)

        # Generate embedding
        embedding = generate_embedding(text)

        # Normalize for cosine similarity (IndexFlatIP)
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        embeddings.append(embedding)
        id_mapping.append(person_id)

        if (i + 1) % 50 == 0:
            print(f"  Processed {i + 1}/{len(people_data)} people...")

    if not embeddings:
        print("No embeddings generated. Index not built.")
        return

    # Convert to numpy array
    embeddings_array = np.array(embeddings, dtype=np.float32)

    # Build FAISS index (IndexFlatIP for inner product / cosine similarity)
    dimension = embeddings_array.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings_array)

    # Store globally
    _faiss_index = index
    _id_mapping = id_mapping

    # Save to disk
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    save_index(str(INDEX_PATH))

    print(f"Index built successfully with {len(id_mapping)} entries.")
    print(f"Embedding provider: {_embedding_provider}")


def search_similar(query: str, k: int = 10) -> list:
    """
    Search for similar people using semantic search.

    Args:
        query: The search query text.
        k: Number of results to return.

    Returns:
        List of (person_id, score) tuples, sorted by relevance.
    """
    global _faiss_index, _id_mapping

    if not query or not query.strip():
        return []

    # Load index if not loaded
    if _faiss_index is None:
        if not load_index(str(INDEX_PATH)):
            return []

    if _faiss_index is None or _id_mapping is None:
        print("No index available for search.")
        return []

    # Generate query embedding
    query_embedding = generate_embedding(query)

    # Normalize for cosine similarity
    norm = np.linalg.norm(query_embedding)
    if norm > 0:
        query_embedding = query_embedding / norm

    # Reshape for FAISS (expects 2D array)
    query_embedding = query_embedding.reshape(1, -1)

    # Search
    k = min(k, len(_id_mapping))  # Don't request more than we have
    scores, indices = _faiss_index.search(query_embedding, k)

    # Build results
    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx >= 0 and idx < len(_id_mapping):  # Valid index
            person_id = _id_mapping[idx]
            results.append((person_id, float(score)))

    return results


def save_index(path: str) -> bool:
    """
    Save FAISS index and mappings to disk.

    Args:
        path: Path to save the FAISS index file.

    Returns:
        True if successful, False otherwise.
    """
    global _faiss_index, _id_mapping

    if _faiss_index is None or _id_mapping is None:
        print("No index to save.")
        return False

    try:
        import faiss

        # Ensure directory exists
        index_path = Path(path)
        index_path.parent.mkdir(parents=True, exist_ok=True)

        # Save FAISS index
        faiss.write_index(_faiss_index, str(index_path))

        # Save ID mapping
        with open(ID_MAPPING_PATH, 'w') as f:
            json.dump(_id_mapping, f)

        # Save embeddings (optional, for debugging/inspection)
        # Note: We reconstruct from index for now since we normalized them
        n_vectors = _faiss_index.ntotal
        dimension = _faiss_index.d
        embeddings = np.zeros((n_vectors, dimension), dtype=np.float32)
        for i in range(n_vectors):
            embeddings[i] = _faiss_index.reconstruct(i)
        np.save(EMBEDDINGS_PATH, embeddings)

        print(f"Index saved to {path}")
        return True

    except Exception as e:
        print(f"Error saving index: {e}")
        return False


def load_index(path: str) -> bool:
    """
    Load FAISS index and mappings from disk.

    Args:
        path: Path to the FAISS index file.

    Returns:
        True if successful, False otherwise.
    """
    global _faiss_index, _id_mapping

    index_path = Path(path)

    if not index_path.exists():
        print(f"Index file not found: {path}")
        return False

    if not ID_MAPPING_PATH.exists():
        print(f"ID mapping file not found: {ID_MAPPING_PATH}")
        return False

    try:
        import faiss

        # Load FAISS index
        _faiss_index = faiss.read_index(str(index_path))

        # Load ID mapping
        with open(ID_MAPPING_PATH, 'r') as f:
            _id_mapping = json.load(f)

        print(f"Index loaded from {path} with {len(_id_mapping)} entries.")
        return True

    except ImportError:
        print("faiss package not installed. Install with: pip install faiss-cpu")
        return False
    except Exception as e:
        print(f"Error loading index: {e}")
        return False


def get_index_stats() -> dict:
    """Get statistics about the loaded index."""
    global _faiss_index, _id_mapping

    if _faiss_index is None:
        load_index(str(INDEX_PATH))

    if _faiss_index is None:
        return {
            "loaded": False,
            "count": 0,
            "dimension": 0,
            "provider": None
        }

    return {
        "loaded": True,
        "count": _faiss_index.ntotal,
        "dimension": _faiss_index.d,
        "provider": _embedding_provider,
        "index_path": str(INDEX_PATH),
        "id_mapping_path": str(ID_MAPPING_PATH)
    }


def rebuild_from_database() -> None:
    """Rebuild index from database (convenience function)."""
    from database import search_people

    # Get all people from database
    people = search_people(limit=10000)

    if not people:
        print("No people found in database.")
        return

    build_index(people)


if __name__ == "__main__":
    # Test the module
    print("Embeddings module")
    print(f"API available: {is_available()}")
    print(f"Voyage API key: {'set' if VOYAGE_API_KEY else 'not set'}")
    print(f"OpenAI API key: {'set' if OPENAI_API_KEY else 'not set'}")

    stats = get_index_stats()
    print(f"Index stats: {stats}")

    if is_available():
        print("\nTesting embedding generation...")
        test_text = "Professor of Business Administration specializing in entrepreneurship and innovation"
        embedding = generate_embedding(test_text)
        print(f"Embedding shape: {embedding.shape}")
        print(f"Embedding norm: {np.linalg.norm(embedding):.4f}")
        print(f"Provider: {_embedding_provider}")
