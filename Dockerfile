# Dockerfile para Worker RunPod Serverless con Microsoft TRELLIS (Game Asset PBR + 3DGS)
FROM pytorch/pytorch:2.4.0-cuda12.1-cudnn9-devel

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_PREFER_BINARY=1 \
    SPCONV_ALGO=native \
    ATTN_BACKEND=xformers \
    SPARSE_ATTN_BACKEND=xformers \
    TORCH_CUDA_ARCH_LIST="8.0 8.6 8.9 9.0+PTX"

WORKDIR /app

# Open3D 0.20 requiere GLIBCXX_3.4.30; actualizar la biblioteca de Conda.
RUN conda install -y -c conda-forge "libstdcxx-ng>=12" && conda clean -afy

# 1. Dependencias del sistema (compiladores, librerías gráficas y de malla)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    ninja-build \
    libegl1 \
    libgl1 \
    libgl1-mesa-dev \
    libglib2.0-0 \
    libgomp1 \
    libusb-1.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Instalar dependencias base de Python y utilidades 3D
RUN pip install --no-cache-dir \
    setuptools \
    wheel \
    ninja \
    pillow \
    imageio \
    imageio-ffmpeg \
    tqdm \
    easydict \
    opencv-python-headless \
    scipy \
    rembg \
    onnxruntime \
    trimesh \
    open3d \
    xatlas \
    pyvista \
    pymeshfix \
    igraph \
    "transformers==4.46.3" \
    runpod \
    huggingface_hub

# 3. Instalar paquetes especializados para aceleración 3D
# utils3d
RUN pip install --no-cache-dir git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8

# spconv para convoluciones dispersas en VRAM
RUN pip install --no-cache-dir spconv-cu120

# xformers (aceleración de atención para TRELLIS)
RUN pip install --no-cache-dir xformers==0.0.27.post2 --index-url https://download.pytorch.org/whl/cu121

# kaolin (NVIDIA) para extracción y rasterización de mallas
RUN pip install --no-cache-dir kaolin -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.4.0_cu121.html

# nvdiffrast (NVIDIA Differentiable Rasterizer)
RUN git clone https://github.com/NVlabs/nvdiffrast.git /tmp/nvdiffrast && \
    pip install --no-cache-dir --no-build-isolation /tmp/nvdiffrast && \
    rm -rf /tmp/nvdiffrast

# diffoctreerast
RUN git clone --recurse-submodules https://github.com/JeffreyXiang/diffoctreerast.git /tmp/diffoctreerast && \
    pip install --no-cache-dir --no-build-isolation /tmp/diffoctreerast && \
    rm -rf /tmp/diffoctreerast

# diff-gaussian-rasterization (para 3D Gaussian Splatting)
RUN git clone https://github.com/autonomousvision/mip-splatting.git /tmp/mip-splatting && \
    pip install --no-cache-dir --no-build-isolation /tmp/mip-splatting/submodules/diff-gaussian-rasterization/ && \
    rm -rf /tmp/mip-splatting

# 4. Clonar el repositorio oficial de Microsoft TRELLIS
RUN git clone --depth 1 https://github.com/microsoft/TRELLIS.git /app/trellis_repo && \
    cp -r /app/trellis_repo/trellis /app/trellis && \
    rm -rf /app/trellis_repo

# Comprobar que las dependencias nativas y Python cargan antes de descargar pesos.
RUN python -c "import open3d; from trellis.pipelines import TrellisImageTo3DPipeline"

# 5. Pre-descargar pesos oficiales de TRELLIS desde Hugging Face
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='microsoft/TRELLIS-image-large')"

# 6. Copiar el handler de RunPod
COPY handler.py .

CMD ["python", "-u", "handler.py"]
