FROM python:3.10-slim-buster

WORKDIR /app

# Install build tool
RUN apt-get update && apt-get install -y \
    build-essential \
    libgtk-3-dev \
    libgl1-mesa-dev \
    pkg-config

# Set environment variables for pkg-config (important!)
ENV PKG_CONFIG_PATH="/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig"

COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir

COPY . .

EXPOSE 8080

CMD ["gunicorn", "--bind=0.0.0.0:8080", "main_web_app:app"]