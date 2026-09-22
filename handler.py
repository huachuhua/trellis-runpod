"""
handler.py — Worker Serverless de RunPod para Microsoft TRELLIS (SB-176)
Genera modelos 3D con mallas poligonales limpias (.GLB) y texturas PBR completas
(Base Color, Normales, Rugosidad, Metálico) además de 3D Gaussian Splats (.PLY).
"""

import os
os.environ['SPCONV_ALGO'] = 'native'
os.environ['ATTN_BACKEND'] = 'xformers'
os.environ['SPARSE_ATTN_BACKEND'] = 'xformers'

import io
import time
import base64
import tempfile
import traceback
import torch
import runpod
from PIL import Image
from huggingface_hub import snapshot_download
from result_transport import stream_model_output

from trellis.pipelines import TrellisImageTo3DPipeline
from trellis.utils import postprocessing_utils
from trellis import models as trellis_models

# TRELLIS captura el primer fallo de carga y prueba una ruta alternativa.
# Registrar el error original para diagnosticar checkpoints y dependencias.
_original_model_loader = trellis_models.from_pretrained

def _load_model_with_diagnostics(model_path, *args, **kwargs):
    try:
        return _original_model_loader(model_path, *args, **kwargs)
    except Exception:
        print(f"❌ Falló la carga del checkpoint: {model_path}", flush=True)
        traceback.print_exc()
        raise

trellis_models.from_pretrained = _load_model_with_diagnostics

print("⚡ Configurando worker Serverless para Microsoft TRELLIS...")
device = "cuda" if torch.cuda.is_available() else "cpu"

pipeline = None
pipeline_error = None


def get_pipeline():
    """
    Carga resiliente del pipeline de Microsoft TRELLIS en VRAM.
    """
    global pipeline, pipeline_error
    if pipeline is not None:
        return pipeline, None

    for attempt in range(1, 3):
        try:
            print(f"🚀 [Intento {attempt}/2] Cargando TrellisImageTo3DPipeline desde 'microsoft/TRELLIS-image-large'...")
            device_name = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"   Dispositivo: {device_name} (cuda disponible: {torch.cuda.is_available()})")

            if device_name == "cuda":
                print(f"   GPU: {torch.cuda.get_device_name(0)}")
                print(f"   VRAM Total: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.2f} GB")
                torch.cuda.empty_cache()

            model_path = snapshot_download(repo_id="microsoft/TRELLIS-image-large", local_files_only=True)
            pipe = TrellisImageTo3DPipeline.from_pretrained(model_path)
            if device_name == "cuda":
                pipe.cuda()

            print(f"✅ TRELLIS cargado con éxito en {device_name}")
            pipeline = pipe
            pipeline_error = None
            return pipeline, None

        except Exception as e:
            pipeline_error = f"{type(e).__name__}: {str(e)}"
            print(f"❌ Error cargando TRELLIS (intento {attempt}): {pipeline_error}")
            traceback.print_exc()
            if attempt < 2:
                time.sleep(2)

    return None, pipeline_error


# Pre-cargar en memoria al arrancar el contenedor
get_pipeline()


def handler(job):
    """
    Manejador del trabajo de RunPod Serverless para TRELLIS.
    Entrada esperada en job['input']:
    {
        "image": "<base64_string_or_url>",
        "seed": 42,
        "simplify": 0.95,
        "texture_size": 1024
    }
    """
    job_input = job.get("input", {})
    if "transport_probe_bytes" in job_input:
        size = int(job_input["transport_probe_bytes"])
        if not 1 <= size <= 80 * 1024 * 1024:
            raise ValueError("Tamaño de prueba de transporte inválido")
        yield from stream_model_output(os.urandom(size), b"glTF-transport-probe")
        return
    if job_input.get("output_transport") != "trellis-files-v1":
        yield {"error": "Actualiza y reinicia manualmente el backend de la app para recibir modelos por fragmentos."}
        return
    image_raw = job_input.get("image")
    seed = int(job_input.get("seed", 42))
    simplify = float(job_input.get("simplify", 0.95))
    texture_size = int(job_input.get("texture_size", 1024))

    if not image_raw:
        yield {"error": "No se proporcionó el parámetro 'image' en el input."}
        return

    pipe, err = get_pipeline()
    if pipe is None:
        yield {"error": f"El pipeline de TRELLIS no pudo inicializarse: {err}"}
        return

    try:
        # Decodificar imagen
        if image_raw.startswith("data:image/"):
            image_raw = image_raw.split(",")[1]

        image_bytes = base64.b64decode(image_raw)
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        print(f"🎨 Ejecutando TRELLIS (seed={seed}, simplify={simplify}, texture_size={texture_size})...")

        with torch.no_grad():
            outputs = pipe.run(img, seed=seed)

        # 1. Extraer 3D Gaussian Splats (.PLY)
        ply_bytes = None
        with tempfile.NamedTemporaryFile(suffix=".ply", delete=False) as tmp_ply:
            tmp_ply_path = tmp_ply.name

        try:
            outputs['gaussian'][0].save_ply(tmp_ply_path)
            with open(tmp_ply_path, "rb") as f:
                ply_bytes = f.read()
            print(f"✨ 3D Gaussian Splats extraídos ({len(ply_bytes)} bytes)")
        finally:
            if os.path.exists(tmp_ply_path):
                os.unlink(tmp_ply_path)

        # 2. Extraer Malla Poligonal con Texturas PBR (.GLB)
        print("🧱 Generando malla poligonal con texturas PBR...")
        glb = postprocessing_utils.to_glb(
            outputs['gaussian'][0],
            outputs['mesh'][0],
            simplify=simplify,
            texture_size=texture_size,
            verbose=False
        )

        with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as tmp_glb:
            tmp_glb_path = tmp_glb.name

        try:
            glb.export(tmp_glb_path)
            with open(tmp_glb_path, "rb") as f:
                glb_bytes = f.read()
            print(f"✨ Malla .GLB con texturas PBR generada ({len(glb_bytes)} bytes)")
        finally:
            if os.path.exists(tmp_glb_path):
                os.unlink(tmp_glb_path)

        yield from stream_model_output(ply_bytes, glb_bytes)

    except Exception as e:
        traceback.print_exc()
        print(f"❌ Error durante la inferencia de TRELLIS: {str(e)}")
        yield {"error": str(e)}


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler, "return_aggregate_stream": False})
