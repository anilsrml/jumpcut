# Python 3.11 slim imajını temel al
FROM python:3.11-slim

# FFmpeg'i statik binary olarak Python ile indir ve kur (apt-get gerektirmez)
# Python'un lzma modülü ile xz dosyasını açıyoruz
RUN python3 << 'EOF'
import urllib.request
import lzma
import tarfile
import os
import shutil

# FFmpeg'i indir
url = 'https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz'
urllib.request.urlretrieve(url, '/tmp/ffmpeg.tar.xz')

# xz dosyasını aç
with lzma.open('/tmp/ffmpeg.tar.xz', 'rb') as xz_file:
    with tarfile.open(fileobj=xz_file, mode='r|') as tar:
        tar.extractall('/tmp')

# FFmpeg'i kur
ffmpeg_dir = [d for d in os.listdir('/tmp') if d.startswith('ffmpeg-') and d.endswith('-amd64-static')][0]
shutil.move(f'/tmp/{ffmpeg_dir}/ffmpeg', '/usr/local/bin/ffmpeg')
shutil.move(f'/tmp/{ffmpeg_dir}/ffprobe', '/usr/local/bin/ffprobe')
os.chmod('/usr/local/bin/ffmpeg', 0o755)
os.chmod('/usr/local/bin/ffprobe', 0o755)

# Temizle
shutil.rmtree(f'/tmp/{ffmpeg_dir}')
os.remove('/tmp/ffmpeg.tar.xz')
EOF

# Çalışma dizinini ayarla
WORKDIR /app

# Python bağımlılıklarını kopyala ve yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama dosyalarını kopyala
COPY main.py .

# Port'u expose et
EXPOSE 5000

# Uygulamayı çalıştır
CMD ["python", "main.py"]

