from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import requests
import time
import subprocess
import os
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import tempfile
import uuid

# .env dosyasını yükle
load_dotenv()

app = Flask(__name__)
CORS(app)  # CORS desteği

# Konfigürasyon
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max dosya boyutu
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

base_url = "https://api.assemblyai.com"

# API key'i .env dosyasından al
api_key = os.getenv("ASSEMBLYAI_API_KEY")
if not api_key:
    raise ValueError("ASSEMBLYAI_API_KEY .env dosyasında bulunamadı. Lütfen .env dosyasını kontrol edin.")

headers = {
    "authorization": api_key
}

# FFmpeg kontrolü
def check_ffmpeg():
    """FFmpeg'in kurulu olup olmadığını kontrol et"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

if not check_ffmpeg():
    print("UYARI: FFmpeg bulunamadı! Video işleme çalışmayabilir.")

def process_video(video_path, output_path):
    """Video işleme fonksiyonu"""
    # Video dosyasını AssemblyAI'ye yükle
    print("Video dosyası API'ye yükleniyor...")
    with open(video_path, "rb") as f:
        response = requests.post(base_url + "/v2/upload",
                            headers=headers,
                            data=f)

    if response.status_code != 200:
        raise RuntimeError(f"Video yükleme hatası: {response.status_code} - {response.text}")

    upload_data = response.json()
    if "upload_url" not in upload_data:
        raise RuntimeError(f"Upload URL alınamadı: {upload_data}")

    upload_url = upload_data["upload_url"]

    # Transkript oluştur
    data = {
        "audio_url": upload_url
    }

    url = base_url + "/v2/transcript"
    response = requests.post(url, json=data, headers=headers)

    if response.status_code != 200:
        raise RuntimeError(f"Transkript oluşturma hatası: {response.status_code} - {response.text}")

    transcript_data = response.json()
    if "id" not in transcript_data:
        raise RuntimeError(f"Transkript ID alınamadı: {transcript_data}")

    transcript_id = transcript_data['id']
    polling_endpoint = base_url + "/v2/transcript/" + transcript_id

    # Transkript tamamlanana kadar bekle
    while True:
        response = requests.get(polling_endpoint, headers=headers)
        if response.status_code != 200:
            raise RuntimeError(f"Transkript sorgulama hatası: {response.status_code} - {response.text}")
        
        transcription_result = response.json()
        
        if 'status' not in transcription_result:
            raise RuntimeError(f"Geçersiz transkript yanıtı: {transcription_result}")

        if transcription_result['status'] == 'completed':
            words = transcription_result["words"]
            
            # Kelimeler arasındaki boşlukları tespit et
            segments_to_keep = []
            silence_threshold = 1000  # 1000ms = 1 saniye
            
            if len(words) > 0:
                current_start = words[0]['start'] / 1000.0
                
                for i in range(len(words) - 1):
                    current_end = words[i]['end'] / 1000.0
                    next_start = words[i + 1]['start'] / 1000.0
                    gap = (next_start - current_end) * 1000
                    
                    if gap >= silence_threshold:
                        segments_to_keep.append({
                            'start': current_start,
                            'end': current_end
                        })
                        current_start = next_start
                
                segments_to_keep.append({
                    'start': current_start,
                    'end': words[-1]['end'] / 1000.0
                })
            
            # FFmpeg ile video kesme
            if segments_to_keep:
                filter_parts = []
                for i, segment in enumerate(segments_to_keep):
                    start_time = segment['start']
                    end_time = segment['end']
                    filter_parts.append(f"[0:v]trim=start={start_time}:end={end_time},setpts=PTS-STARTPTS[v{i}];")
                    filter_parts.append(f"[0:a]atrim=start={start_time}:end={end_time},asetpts=PTS-STARTPTS[a{i}];")
                
                concat_video_inputs = "".join([f"[v{i}]" for i in range(len(segments_to_keep))])
                concat_audio_inputs = "".join([f"[a{i}]" for i in range(len(segments_to_keep))])
                num_segments = len(segments_to_keep)
                
                filter_complex = "".join(filter_parts) + f"{concat_video_inputs}concat=n={num_segments}:v=1[outv];{concat_audio_inputs}concat=n={num_segments}:v=0:a=1[outa]"
                
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-i', video_path,
                    '-filter_complex', filter_complex,
                    '-map', '[outv]',
                    '-map', '[outa]',
                    '-c:v', 'libx264',
                    '-c:a', 'aac',
                    '-y',
                    output_path
                ]
                
                result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
                
                if result.returncode != 0:
                    raise RuntimeError(f"FFmpeg hatası: {result.stderr}")
                
                return True

        elif transcription_result['status'] == 'error':
            error_msg = transcription_result.get('error', 'Bilinmeyen hata')
            raise RuntimeError(f"Transkript hatası: {error_msg}")
        
        elif transcription_result['status'] == 'processing':
            time.sleep(3)
        else:
            time.sleep(3)

@app.route('/')
def index():
    return jsonify({
        "message": "Jumpcut Video Processing API",
        "version": "1.0",
        "endpoints": {
            "/": "API bilgileri",
            "/health": "Sağlık kontrolü",
            "/process": "Video işleme (POST)"
        }
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/process', methods=['POST'])
def process():
    """Video işleme endpoint'i"""
    if 'video' not in request.files:
        return jsonify({"error": "Video dosyası bulunamadı"}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({"error": "Dosya seçilmedi"}), 400
    
    # Geçici dosya yolları
    file_id = str(uuid.uuid4())
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"input_{file_id}.mp4")
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"output_{file_id}.mp4")
    
    try:
        # Dosyayı kaydet
        file.save(input_path)
        
        # Video işle
        process_video(input_path, output_path)
        
        # İşlenmiş videoyu gönder
        return send_file(
            output_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name=f"processed_{file.filename}"
        )
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    finally:
        # Geçici dosyaları temizle
        for path in [input_path, output_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

