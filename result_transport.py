"""Keep model results below RunPod's inline response limit."""
import base64
import gzip
import json
import hashlib

# Leave room for the RunPod SDK envelope on the asynchronous /run API.
MAX_INLINE_BYTES = 10 * 1024 * 1024 - 64 * 1024


def build_model_output(ply_bytes, glb_bytes, compression="none", *, max_bytes=MAX_INLINE_BYTES):
    if not ply_bytes:
        raise ValueError("TRELLIS no generó un archivo PLY válido.")
    if compression not in ("none", "gzip"):
        raise ValueError("Compresión de salida no admitida.")
    result = {
        "status": "success", "engine": "trellis", "pbr": True,
        "ply_size_bytes": len(ply_bytes), "glb_size_bytes": len(glb_bytes or b""),
    }
    for kind, data in (("ply", ply_bytes), ("glb", glb_bytes)):
        if data:
            encoded = gzip.compress(data, compresslevel=6, mtime=0) if compression == "gzip" else data
            key = f"{kind}_gzip_base64" if compression == "gzip" else f"{kind}_base64"
            result[key] = base64.b64encode(encoded).decode("ascii")
    wire_bytes = len(json.dumps({"output": result}, ensure_ascii=False).encode("utf-8"))
    print(f"Salida TRELLIS: PLY={len(ply_bytes)} bytes, GLB={len(glb_bytes or b'')} bytes, "
          f"JSON={wire_bytes} bytes, compresión={compression}", flush=True)
    if wire_bytes > max_bytes:
        raise ValueError(
            f"El modelo ocupa {wire_bytes / 1048576:.2f} MiB al transferirse y supera "
            f"el límite seguro de {max_bytes / 1048576:.2f} MiB de RunPod. "
            + ("Activa la transferencia comprimida actualizando el backend de la app."
               if compression == "none" else
               "Actualiza la app para utilizar la transferencia por fragmentos, sin reducir la calidad.")
        )
    return result


STREAM_PROTOCOL = "trellis-files-v1"
CHUNK_BYTES = 256 * 1024


def stream_model_output(ply_bytes, glb_bytes):
    """Lossless transfer: each JSON event stays below RunPod's 1 MB limit."""
    if not ply_bytes:
        raise ValueError("TRELLIS no generó un archivo PLY válido.")
    files = {kind: data for kind, data in (("ply", ply_bytes), ("glb", glb_bytes)) if data}
    manifest = {
        kind: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
               "chunks": (len(data) + CHUNK_BYTES - 1) // CHUNK_BYTES}
        for kind, data in files.items()
    }
    yield {"protocol": STREAM_PROTOCOL, "type": "manifest", "files": manifest,
           "chunk_bytes": CHUNK_BYTES}
    for kind, data in files.items():
        for index, offset in enumerate(range(0, len(data), CHUNK_BYTES)):
            chunk = gzip.compress(data[offset:offset + CHUNK_BYTES], compresslevel=6, mtime=0)
            yield {"protocol": STREAM_PROTOCOL, "type": "chunk", "file": kind,
                   "index": index, "data": base64.b64encode(chunk).decode("ascii")}
    yield {"protocol": STREAM_PROTOCOL, "type": "complete"}
