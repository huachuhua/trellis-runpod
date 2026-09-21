# Worker RunPod Serverless: Microsoft TRELLIS (Game Asset PBR + 3DGS)

Este worker empaqueta **Microsoft TRELLIS** (`microsoft/TRELLIS-image-large`) en un contenedor Docker optimizado para **RunPod Serverless**.

---

## Capacidades

1. **Malla Poligonal con Materiales PBR**: Genera un archivo `.glb` con UV unwrapping y mapas de texturas completos (Color, Normales, Rugosidad, Metálico). Compatible directamente con Blender, Unity y Unreal Engine 5.
2. **3D Gaussian Splats**: Exporta el archivo `.ply` volumétrico para inspección en el visor cinemático **PlayCanvas** de SB-176 o SuperSplat.

---

## Despliegue en RunPod

1. **Crear repositorio en GitHub**:
   - Crea un repositorio en GitHub (ej. `trellis-runpod`).
   - Sube el contenido de esta carpeta `worker-trellis/`.
   - GitHub Actions compilará la imagen y la publicará en:
     `ghcr.io/<tu-usuario>/trellis-runpod:latest`

2. **Crear Endpoint Serverless en RunPod**:
   - Ve a **Serverless** -> **New Endpoint**.
   - **Container Image**: `ghcr.io/<tu-usuario>/trellis-runpod:latest`
   - **GPU**: NVIDIA GeForce RTX 4090 (24 GB VRAM) o RTX 3090.
   - **Workers Min**: 0 (para que cueste $0 en reposo).
   - **Workers Max**: 3.
   - **Idle Timeout**: 60s.

3. **Configurar en Second Brain**:
   - En la configuración de SB-176, añade el ID del nuevo endpoint en el campo `RunPod TRELLIS Endpoint ID`.
