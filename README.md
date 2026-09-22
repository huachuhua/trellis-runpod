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

## Transferencia de resultados

El backend solicita `output_compression: "gzip"` para recibir `ply_gzip_base64` y
`glb_gzip_base64`. Se descomprimen en Second Brain antes de guardar los archivos;
la compresión no altera la malla ni los splats. Las solicitudes sin esa opción
siguen usando los campos base64 originales.

El worker registra los tamaños y rechaza de forma explícita salidas que superan
el límite preventivo de 10 MiB menos 64 KiB, en lugar de entregar un JSON demasiado
grande. Esto requiere actualizar también `backend.mjs` de SB-176 y reiniciar
manualmente Second Brain para activar la transferencia comprimida.

Prueba local sin GPU: `python3 -B -m unittest test_result_transport.py`.


## Transferencia de modelos grandes (trellis-files-v1)

El handler ahora es un generador: `/stream/{jobId}` entrega un manifiesto con
SHA-256 y tamaños, fragmentos gzip de 256 KiB de datos originales y un evento
`complete`. `return_aggregate_stream` está desactivado: `/status` NO contiene
los archivos. La app debe leer `/stream` mediante un único consumidor por
trabajo, guardar los fragmentos y comprobar ambos hashes antes de publicar el
modelo. Cada evento es inferior a 1 MB, independientemente del tamaño total.
No se reducen resolución, geometría ni textura. El receptor local admite hasta
1 GiB por archivo; requiere espacio para fragmentos y archivos reconstruidos.
RunPod conserva los resultados temporalmente: la app debe recibirlos antes de
su caducidad. Una respuesta de red perdida después de drenar `/stream` puede
requerir repetir el trabajo; el checksum impide guardar archivos incompletos.

Actualizar el backend y reiniciarlo MANUALMENTE antes de generar con este worker.
`Dockerfile.transport` reutiliza la imagen de dependencias ya validada; el
Dockerfile completo queda disponible para recompilaciones de dependencias.

Diagnóstico sin inferencia: `input.transport_probe_bytes` (1–80 MiB) genera datos
aleatorios y los transfiere mediante el mismo protocolo. No crea un modelo.
