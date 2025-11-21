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

"""
Jumpcut Video Processing API
Render.com için optimize edilmiş Flask uygulaması

Özellikler:
- Çoklu video işleme (sınırsız sayıda video)
- AssemblyAI ile otomatik transkript
- Jumpcut işleme (sessizlik kesme)
- FFmpeg ile video birleştirme
- Render.com uyumlu (geçici dosya sistemi kullanır)
"""

app = Flask(__name__)
CORS(app)  # CORS desteği

# Konfigürasyon
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max dosya boyutu
# Render.com için geçici klasör kullan (kalıcı dosya sistemi yok)
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

def concatenate_videos(video_paths, output_path):
    """Birden fazla videoyu FFmpeg ile birleştirir"""
    if not video_paths:
        raise ValueError("Birleştirilecek video dosyası bulunamadı")
    
    # Geçici dosya listesi oluştur
    list_file_path = os.path.join(tempfile.gettempdir(), f"concat_list_{uuid.uuid4().hex}.txt")
    
    try:
        # FFmpeg concat için dosya listesi oluştur
        with open(list_file_path, 'w', encoding='utf-8') as f:
            for video_path in video_paths:
                if not os.path.exists(video_path):
                    raise FileNotFoundError(f"Video dosyası bulunamadı: {video_path}")
                # FFmpeg concat formatı: file 'path/to/video.mp4'
                f.write(f"file '{os.path.abspath(video_path)}'\n")
        
        # FFmpeg ile videoları birleştir
        ffmpeg_cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', list_file_path,
            '-c', 'copy',
            '-y',
            output_path
        ]
        
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"Video birleştirme hatası: {result.stderr}")
        
        print(f"Videolar başarıyla birleştirildi: {output_path}")
        return True
    
    finally:
        # Geçici liste dosyasını temizle
        if os.path.exists(list_file_path):
            try:
                os.remove(list_file_path)
            except:
                pass

@app.route('/')
def index():
    return jsonify({
        "message": "Jumpcut Video Processing API",
        "version": "2.0",
        "endpoints": {
            "/": "API bilgileri",
            "/health": "Sağlık kontrolü",
            "/process": "Çoklu video işleme ve birleştirme (POST) - videos field'ı ile birden fazla video gönderilebilir"
        }
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/process', methods=['POST'])
def process():
    """Çoklu video işleme ve birleştirme endpoint'i - Kaç video yüklenirse yüklensin işler"""
    # Hem 'videos' (yeni format) hem 'video' (eski format) desteği
    if 'videos' in request.files:
        files = request.files.getlist('videos')
    elif 'video' in request.files:
        # Eski format desteği - tek video'yu liste olarak al
        files = [request.files['video']]
    else:
        return jsonify({"error": "Video dosyaları bulunamadı. 'videos' field'ı ile video gönderin."}), 400
    
    if not files or len(files) == 0:
        return jsonify({"error": "Dosya seçilmedi"}), 400
    
    # Render.com için geçici klasör kullan (kalıcı dosya sistemi yok)
    output_dir = app.config['UPLOAD_FOLDER']
    
    # Geçici dosya yolları
    temp_inputs = []
    temp_outputs = []
    final_output_path = None
    
    try:
        # Dosyaları kaydet ve işle
        valid_files = [f for f in files if f.filename != '']
        
        if len(valid_files) == 0:
            return jsonify({"error": "Geçerli video dosyası bulunamadı"}), 400
        
        print(f"Toplam {len(valid_files)} video işlenecek...")
        
        for idx, file in enumerate(valid_files, start=1):
            file_id = str(uuid.uuid4())
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"input_{file_id}.mp4")
            file.save(input_path)
            temp_inputs.append(input_path)
            
            output_filename = f"output_{file_id}_{idx}.mp4"
            output_path = os.path.join(output_dir, output_filename)
            temp_outputs.append(output_path)
            
            # Video işle
            print(f"[{idx}/{len(valid_files)}] Video işleniyor: {file.filename}")
            process_video(input_path, output_path)
        
        # Videoları birleştir
        final_file_id = str(uuid.uuid4())
        final_output_path = os.path.join(output_dir, f"final_output_{final_file_id}.mp4")
        
        if len(temp_outputs) > 1:
            print(f"\n{len(temp_outputs)} video birleştiriliyor...")
            concatenate_videos(temp_outputs, final_output_path)
        else:
            # Tek video varsa, final_output olarak kopyala
            import shutil
            shutil.copy2(temp_outputs[0], final_output_path)
        
        print(f"✓ Final çıktı hazır: {final_output_path}")
        
        # Final videoyu gönder
        return send_file(
            final_output_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name="final_output.mp4"
        )
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    finally:
        # Geçici dosyaları temizle
        cleanup_paths = temp_inputs + temp_outputs
        if final_output_path:
            cleanup_paths.append(final_output_path)
        
        for path in cleanup_paths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

