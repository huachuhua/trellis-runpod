"""
handler.py — Worker Serverless de RunPod para Microsoft TRELLIS (SB-176)
Genera modelos 3D con mallas poligonales limpias (.GLB) y texturas PBR completas
(Base Color, Normales, Rugosidad, Metálico) además de 3D Gaussian Splats (.PLY).
"""

import os
os.environ['SPCONV_ALGO'] = 'native'

import io
import time
import base64
import tempfile
import traceback
import torch
import runpod
from PIL import Image

from trellis.pipelines import TrellisImageTo3DPipeline
from trellis.utils import postprocessing_utils

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

            pipe = TrellisImageTo3DPipeline.from_pretrained("microsoft/TRELLIS-image-large")
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
    image_raw = job_input.get("image")
    seed = int(job_input.get("seed", 42))
    simplify = float(job_input.get("simplify", 0.95))
    texture_size = int(job_input.get("texture_size", 1024))

    if not image_raw:
        return {"error": "No se proporcionó el parámetro 'image' en el input."}

    pipe, err = get_pipeline()
    if pipe is None:
        return {"error": f"El pipeline de TRELLIS no pudo inicializarse: {err}"}

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

        return {
            "status": "success",
            "engine": "trellis",
            "pbr": true,
            "ply_base64": base64.b64encode(ply_bytes).decode("utf-8") if ply_bytes else None,
            "glb_base64": base64.b64encode(glb_bytes).decode("utf-8") if glb_bytes else None,
            "ply_size_bytes": len(ply_bytes) if ply_bytes else 0,
            "glb_size_bytes": len(glb_bytes) if glb_bytes else 0
        }

    except Exception as e:
        traceback.print_exc()
        print(f"❌ Error durante la inferencia de TRELLIS: {str(e)}")
        return {"error": str(e)}


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
