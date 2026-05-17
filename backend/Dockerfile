# Backend Dockerfile
# Python 3.11 slim — small base, fast builds
FROM python:3.11-slim

# System packages
#  git              – GitPython binary requirement
#  build-essential  – compiles C extensions (tree-sitter, scipy)
#  curl             – lightweight HTTP tool (optional local debugging)
#  libgomp1         – OpenMP runtime required by PyTorch / numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        build-essential \
        curl \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

#Python dependencies (layer-cache order)
COPY requirements.txt .

# 1. Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# 1b. Pin NumPy to 1.x BEFORE any compiled extension is installed.
#     torch 2.2.x and PyG wheels are built against NumPy 1.x ABI;
#     installing numpy first prevents any later dep from upgrading to 2.x.
RUN pip install --no-cache-dir "numpy==1.26.4"

# 2. CPU-only PyTorch (avoids the ~2 GB CUDA wheel)
RUN pip install --no-cache-dir \
        torch==2.2.2 torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cpu

# 3. PyTorch Geometric + required sparse/scatter extensions (CPU wheels)
#    Must be installed AFTER torch and AGAINST the same torch version.
RUN pip install --no-cache-dir torch_geometric==2.5.3
RUN pip install --no-cache-dir \
        torch_scatter \
        torch_sparse \
        torch_cluster \
        torch_spline_conv \
        -f https://data.pyg.org/whl/torch-2.2.2+cpu.html

# 4. Everything else from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

#Application source
COPY . .

EXPOSE 8000

# Uvicorn: bind to 0.0.0.0 so Docker port-mapping works.
# No --reload in production image; add a volume mount for dev hot-reload.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
