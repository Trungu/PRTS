# PRTS Engineering Bot — sandboxed code-execution image.
#
# Security model (enforced by docker_manager.py at runtime):
#   --runtime=runsc                        gVisor kernel sandbox
#   --network none                         no outbound or inbound network
#   --read-only                            host FS is immutable; /tmp is ephemeral tmpfs
#                                          /workspace is a PERSISTENT bind mount
#   --cap-drop=ALL                         all Linux capabilities dropped
#   --security-opt no-new-privileges:true  blocks setuid escalation
#   --memory 1024m / --memory-swap 1024m   1 GB RAM cap, swap disabled
#   --cpus 2                               CPU cap
#
# Build:  docker build -t ai_sandbox_image .
#
# /workspace is bind-mounted from sandbox_workspace/ in the project root —
# files written there survive container restarts and image rebuilds.

FROM python:3.13-slim

LABEL description="PRTS Engineering Bot – sandboxed Python/Java execution environment" \
      org.opencontainers.image.title="prts-sandbox"

# ── System packages ───────────────────────────────────────────────────────────
# build-essential   : gcc/g++ for compiled Python extensions and inline C/C++
# libfreetype6-dev,
# libpng-dev        : matplotlib native rasteriser
# libhdf5-dev,
# pkg-config        : required by h5py
# libgraphviz-dev   : required by pygraphviz
# poppler-utils     : PDF utilities (pdfinfo, pdftotext …)
# default-jdk       : full Java development kit — javac + java for engineering code
# graphviz          : graph layout engine used by networkx / pygraphviz
# imagemagick       : image conversion and manipulation (convert, identify …)
# git               : version control inside the workspace
# bc                : arbitrary-precision CLI calculator
# gnuplot-nox       : non-interactive plotting (PNG output, no X11 required)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libfreetype6-dev \
        libpng-dev \
        libhdf5-dev \
        pkg-config \
        libgraphviz-dev \
        poppler-utils \
        default-jdk \
        graphviz \
        imagemagick \
        git \
        bc \
        gnuplot-nox \
    && rm -rf /var/lib/apt/lists/*

# ── Python scientific / engineering stack ────────────────────────────────────
RUN pip install --no-cache-dir \
        numpy scipy sympy \
        matplotlib seaborn \
        pandas openpyxl xlrd pyarrow statsmodels \
        scikit-learn scikit-image \
        pint control uncertainties \
        cvxpy \
        networkx pygraphviz \
        pypdf pillow python-docx h5py \
        beautifulsoup4 lxml \
        tqdm joblib tabulate shapely requests

# ── Non-root sandbox user ─────────────────────────────────────────────────────
RUN useradd -m -u 1000 sandboxuser

# Create help.txt so docker_manager._ensure_help_file() can copy it to /workspace.
RUN { \
    echo 'PRTS Engineering Sandbox'; \
    echo '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'; \
    echo 'Python 3.13 + Java JDK  |  /workspace is PERSISTENT (bind mount)'; \
    echo ''; \
    echo 'Python packages:'; \
    echo '  numpy  scipy  sympy  matplotlib  seaborn  pandas  statsmodels'; \
    echo '  scikit-learn  scikit-image  openpyxl  xlrd  pyarrow  h5py'; \
    echo '  pint  control  cvxpy  uncertainties'; \
    echo '  networkx  pygraphviz  beautifulsoup4  lxml'; \
    echo '  pypdf  pillow  python-docx  tqdm  joblib  tabulate  shapely'; \
    echo ''; \
    echo 'Other runtimes:'; \
    echo '  java     — compile: javac File.java   run: java ClassName'; \
    echo '  gcc/g++  — compile: gcc file.c -o out  (build-essential installed)'; \
    echo '  bc       — arbitrary-precision calculator  (echo "scale=10; 2^50" | bc)'; \
    echo '  gnuplot  — non-interactive plotting (set terminal pngcairo)'; \
    echo '  dot      — Graphviz graph layout'; \
    echo '  convert  — ImageMagick image conversion'; \
    echo '  git      — version control'; \
    echo ''; \
    echo 'Working paths:'; \
    echo '  /workspace  — PERSISTENT bind mount (survives restarts and rebuilds)'; \
    echo '  /tmp        — ephemeral tmpfs (cleared on restart)'; \
    echo ''; \
    echo 'Restrictions:'; \
    echo '  * No network access'; \
    echo '  * No privilege escalation'; \
    echo '  * Max 1 GB RAM, 2 CPUs'; \
    echo '  * Command timeout 60 s'; \
    } > /home/sandboxuser/help.txt \
    && chmod 444 /home/sandboxuser/help.txt

USER sandboxuser
WORKDIR /workspace

# Non-interactive matplotlib backend — no display available inside the container.
ENV MPLBACKEND=Agg
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
