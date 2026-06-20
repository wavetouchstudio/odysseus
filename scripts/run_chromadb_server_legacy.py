"""Standalone ChromaDB 1.5.9 server forced onto the legacy pre-Rust SegmentAPI.

chromadb 1.5.9 defaults chroma_api_impl to chromadb.api.rust.RustBindingsAPI,
which requires the chromadb_rust_bindings wheel — unpublished for this
platform. SegmentAPI is the pure-Python implementation that predates the Rust
core rewrite and is still bundled in 1.5.9. Forcing it here lets the server
match the version of chromadb-client already installed in the main app
environment, so client and server speak the same wire protocol.
"""
import os
import uvicorn
from chromadb.config import Settings
from chromadb.server.fastapi import FastAPI

settings = Settings(
    chroma_api_impl="chromadb.api.segment.SegmentAPI",
    is_persistent=True,
    persist_directory=os.path.join(os.path.dirname(__file__), "..", "data", "chromadb_storage"),
    anonymized_telemetry=False,
)
server = FastAPI(settings)

if __name__ == "__main__":
    uvicorn.run(server.app(), host="localhost", port=8100, log_level="info")
