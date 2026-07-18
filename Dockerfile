FROM python:3.10.14-slim

# System dependencies: ffmpeg, wget, curl, git, CA certs, gnupg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    curl \
    git \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20 from NodeSource (required by tiktokautouploader JavaScript deps)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Playwright / Phantomwright Chromium system dependencies
RUN apt-get update && apt-get install -y \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    libxshmfence1 \
    libglu1-mesa \
    libx11-xcb1 \
    libxcursor1 \
    libxi6 \
    libxtst6 \
    libnss3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/video_bot

# ── Layer 1: pip dependencies (cached unless requirements change) ──
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Layer 2: spaCy model ──
RUN python -m spacy download en_core_web_sm

# ── Layer 3: tiktokautouploader (--no-deps avoids inference/torch conflict) ──
RUN pip install --no-cache-dir tiktokautouploader==6.1 --no-deps && \
    pip install --no-cache-dir phantomwright>=0.1.5 pillow requests scikit-learn setuptools

# ── Layer 4: browser binaries (large, cached) ──
RUN python -m playwright install --with-deps chromium
RUN phantomwright_driver install chromium

# ── Layer 5: upstream video_bot code (flatten into WORKDIR) ──
COPY video_bot/ .

# ── Layer 6: our new pipeline files (overlay on top) ──
COPY run_pipeline.py .
COPY init_config.py .
COPY rewrite_story.py .
COPY subtitle_generator.py .
COPY upload_tiktok.py .
COPY upload_instagram.py .
COPY upload_youtube.py .
COPY scripts/ ./scripts/

CMD ["python3", "run_pipeline.py"]
