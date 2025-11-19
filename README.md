# Jumpcut - Video Boşluk Kesme Servisi (Docker)

Bu proje, videolardaki uzun sessizlikleri otomatik olarak tespit edip kesen bir web servisidir. AssemblyAI API kullanarak transkript oluşturur ve FFmpeg ile video işleme yapar.

## 🚀 Özellikler

- 🎥 Video yükleme ve işleme
- 🤖 AssemblyAI ile otomatik transkript
- ✂️ Uzun sessizlikleri otomatik kesme (1 saniye eşik)
- 🐳 Docker desteği (FFmpeg dahil)
- 🌐 RESTful API
- 📦 Docker Compose ile kolay kurulum

## 📋 Gereksinimler

- Docker ve Docker Compose
- AssemblyAI API anahtarı

## 🛠️ Kurulum

### 1. Repository'yi klonlayın

```bash
git clone https://github.com/anilsrml/jumpcut.git
cd jumpcut
```

### 2. Environment dosyası oluşturun

`.env` dosyası oluşturun ve API anahtarınızı ekleyin:

```bash
ASSEMBLYAI_API_KEY=your_api_key_here
```

### 3. Docker ile çalıştırın

```bash
docker-compose up --build
```

Uygulama `http://localhost:5000` adresinde çalışacaktır.

## 📡 API Kullanımı

### Sağlık Kontrolü

```bash
GET /health
```

**Örnek:**
```bash
curl http://localhost:5000/health
```

### Ana Endpoint

```bash
GET /
```

API bilgilerini döner.

### Video İşleme

```bash
POST /process
Content-Type: multipart/form-data
```

**Form Data:**
- `video`: (file) Video dosyası (MP4, AVI, MOV, MKV)

**Örnek cURL:**
```bash
curl -X POST http://localhost:5000/process \
  -F "video=@input/video.mp4" \
  -o output.mp4
```

**Python Örneği:**
```python
import requests

url = "http://localhost:5000/process"
files = {'video': open('input/video.mp4', 'rb')}
response = requests.post(url, files=files)

with open('output.mp4', 'wb') as f:
    f.write(response.content)
```

**Test Scripti:**
```bash
# Temel testler
python test_api.py

# Video işleme testi
python test_api.py input/video.mp4
```

## 🐳 Docker Detayları

### Dockerfile

- Python 3.11 slim base image
- FFmpeg statik binary olarak kurulur (repository bağımlılığı yok)
- Flask web servisi

### Docker Compose

- Port mapping: `5000:5000`
- Environment variables: `.env` dosyasından yüklenir
- Geçici dosyalar için volume desteği

## 📁 Proje Yapısı

```
jumpcut/
├── main.py              # Flask web servisi
├── Dockerfile           # Docker imaj tanımı
├── docker-compose.yml   # Docker Compose konfigürasyonu
├── requirements.txt    # Python bağımlılıkları
├── test_api.py         # API test scripti
├── .env.example        # Environment variable şablonu
├── .gitignore          # Git ignore dosyası
└── README.md           # Bu dosya
```

## ⚙️ Konfigürasyon

### Environment Variables

- `ASSEMBLYAI_API_KEY`: AssemblyAI API anahtarınız (zorunlu)
- `PORT`: Flask port numarası (varsayılan: 5000)

### Ayarlar

- **Maksimum dosya boyutu:** 500MB
- **Desteklenen formatlar:** MP4, AVI, MOV, MKV
- **Sessizlik eşiği:** 1 saniye (1000ms)

## 🔧 Geliştirme

### Yerel Geliştirme (Docker olmadan)

1. Python 3.11+ ve FFmpeg kurun
2. Bağımlılıkları yükleyin:
   ```bash
   pip install -r requirements.txt
   ```
3. `.env` dosyasını oluşturun
4. Uygulamayı çalıştırın:
   ```bash
   python main.py
   ```

### Docker Build

```bash
docker build -t jumpcut-docker .
docker run -p 5000:5000 --env-file .env jumpcut-docker
```

## 📝 Notlar

- İşlenmiş videolar geçici olarak saklanır ve otomatik temizlenir
- Video işleme süresi videonun uzunluğuna bağlıdır
- FFmpeg Docker container içinde statik binary olarak kurulur

## 📄 Lisans

MIT

## 🔗 Bağlantılar

- [AssemblyAI](https://www.assemblyai.com/)
- [FFmpeg](https://ffmpeg.org/)

