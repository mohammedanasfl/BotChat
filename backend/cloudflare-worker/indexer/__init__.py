"""Offline knowledge indexer: markdown -> chunks -> Gemini embeddings -> Cloudflare Vectorize.

Lives outside `src/`, so it is never bundled into the Worker.
"""
