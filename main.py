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
from datetime import datetime
from collections import deque
from threading import Lock

# .env dosyasını yükle
load_dotenv()

app = Flask(__name__)
CORS(app)  # CORS desteği

# Konfigürasyon
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max dosya boyutu
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

# ============================================================================
# LOG YÖNETİM SİSTEMİ
# ============================================================================

class LogManager:
    """In-memory log yönetim sistemi"""
    
    def __init__(self, max_logs=1000):
        self.max_logs = max_logs
        self.logs = deque(maxlen=max_logs)  # Son N log mesajını tutar
        self.job_logs = {}  # job_id -> log listesi
        self.job_status = {}  # job_id -> status bilgisi
        self.lock = Lock()  # Thread-safe işlemler için
    
    def add_log(self, level, message, job_id=None, metadata=None):
        """Log mesajı ekle ve konsola yazdır"""
        timestamp = datetime.utcnow().isoformat() + 'Z'
        log_entry = {
            'timestamp': timestamp,
            'level': level,  # INFO, WARNING, ERROR, SUCCESS
            'message': message,
            'job_id': job_id,
            'metadata': metadata or {}
        }
        
        # Konsola yazdır (geliştirme ve debug için)
        level_symbols = {
            'INFO': 'ℹ️',
            'SUCCESS': '✅',
            'WARNING': '⚠️',
            'ERROR': '❌'
        }
        symbol = level_symbols.get(level, '•')
        
        # Konsol çıktısı formatla
        console_msg = f"[{timestamp}] {symbol} [{level}] {message}"
        
        # Metadata varsa ekle
        if metadata:
            metadata_strs = []
            for key, value in metadata.items():
                if key not in ['job_id']:  # job_id zaten ayrı gösteriliyor
                    metadata_strs.append(f"{key}={value}")
            if metadata_strs:
                console_msg += f" | {' | '.join(metadata_strs)}"
        
        # Job ID varsa ekle
        if job_id:
            console_msg += f" | job_id={job_id[:8]}..."
        
        print(console_msg)
        
        with self.lock:
            self.logs.append(log_entry)
            
            # Job bazlı log takibi
            if job_id:
                if job_id not in self.job_logs:
                    self.job_logs[job_id] = deque(maxlen=500)
                self.job_logs[job_id].append(log_entry)
    
    def get_logs(self, job_id=None, limit=100):
        """Log mesajlarını getir"""
        with self.lock:
            if job_id:
                if job_id in self.job_logs:
                    logs = list(self.job_logs[job_id])
                    return logs[-limit:] if limit else logs
                return []
            else:
                logs = list(self.logs)
                return logs[-limit:] if limit else logs
    
    def update_job_status(self, job_id, status, metadata=None):
        """Job durumunu güncelle"""
        with self.lock:
            if job_id not in self.job_status:
                self.job_status[job_id] = {
                    'created_at': datetime.utcnow().isoformat() + 'Z',
                    'status': status,
                    'metadata': {}
                }
            else:
                self.job_status[job_id]['status'] = status
                if 'updated_at' not in self.job_status[job_id]:
                    self.job_status[job_id]['updated_at'] = []
                self.job_status[job_id]['updated_at'].append(datetime.utcnow().isoformat() + 'Z')
            
            if metadata:
                self.job_status[job_id]['metadata'].update(metadata)
    
    def get_job_status(self, job_id):
        """Job durumunu getir"""
        with self.lock:
            return self.job_status.get(job_id, None)
    
    def get_all_jobs(self):
        """Tüm job'ları getir"""
        with self.lock:
            return dict(self.job_status)

# Global log manager instance
log_manager = LogManager()

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

# Başlangıç kontrolleri ve log kayıtları
ffmpeg_available = check_ffmpeg()
api_key_available = bool(os.getenv("ASSEMBLYAI_API_KEY"))

if ffmpeg_available:
    log_manager.add_log("SUCCESS", "FFmpeg kurulum kontrolü başarılı")
else:
    log_manager.add_log("WARNING", "FFmpeg bulunamadı! Video işleme çalışmayabilir.")

if api_key_available:
    log_manager.add_log("SUCCESS", "API key yüklendi")
else:
    log_manager.add_log("ERROR", "API key bulunamadı! ASSEMBLYAI_API_KEY .env dosyasında bulunamadı.")

def process_video(video_path, output_path, job_id=None, video_num=None, video_name=None):
    """Video işleme fonksiyonu"""
    step_start_time = time.time()
    
    # AssemblyAI'ye yükleme başladı
    log_manager.add_log("INFO", "AssemblyAI'ye yükleme başladı", job_id, {
        'video_num': video_num,
        'video_name': video_name
    })
    
    upload_start_time = time.time()
    with open(video_path, "rb") as f:
        response = requests.post(base_url + "/v2/upload",
                            headers=headers,
                            data=f)

    if response.status_code != 200:
        error_msg = f"Video yükleme hatası: {response.status_code} - {response.text}"
        log_manager.add_log("ERROR", error_msg, job_id, {'video_num': video_num})
        raise RuntimeError(error_msg)

    upload_data = response.json()
    if "upload_url" not in upload_data:
        error_msg = f"Upload URL alınamadı: {upload_data}"
        log_manager.add_log("ERROR", error_msg, job_id, {'video_num': video_num})
        raise RuntimeError(error_msg)

    upload_url = upload_data["upload_url"]
    upload_duration = int((time.time() - upload_start_time) * 1000)
    
    # AssemblyAI'ye yükleme tamamlandı
    log_manager.add_log("SUCCESS", f"AssemblyAI'ye yükleme tamamlandı (upload_url alındı)", job_id, {
        'video_num': video_num,
        'duration_ms': upload_duration
    })

    # Transkript oluşturma başladı
    log_manager.add_log("INFO", "Transkript oluşturma başladı", job_id, {'video_num': video_num})
    
    data = {
        "audio_url": upload_url
    }

    url = base_url + "/v2/transcript"
    response = requests.post(url, json=data, headers=headers)

    if response.status_code != 200:
        error_msg = f"Transkript oluşturma hatası: {response.status_code} - {response.text}"
        log_manager.add_log("ERROR", error_msg, job_id, {'video_num': video_num})
        raise RuntimeError(error_msg)

    transcript_data = response.json()
    if "id" not in transcript_data:
        error_msg = f"Transkript ID alınamadı: {transcript_data}"
        log_manager.add_log("ERROR", error_msg, job_id, {'video_num': video_num})
        raise RuntimeError(error_msg)

    transcript_id = transcript_data['id']
    log_manager.add_log("SUCCESS", f"Transkript oluşturma başladı (transcript_id: {transcript_id})", job_id, {
        'video_num': video_num,
        'transcript_id': transcript_id
    })
    
    polling_endpoint = base_url + "/v2/transcript/" + transcript_id
    last_status = None
    status_check_count = 0

    # Transkript tamamlanana kadar bekle
    while True:
        response = requests.get(polling_endpoint, headers=headers)
        if response.status_code != 200:
            error_msg = f"Transkript sorgulama hatası: {response.status_code} - {response.text}"
            log_manager.add_log("ERROR", error_msg, job_id, {'video_num': video_num})
            raise RuntimeError(error_msg)
        
        transcription_result = response.json()
        
        if 'status' not in transcription_result:
            error_msg = f"Geçersiz transkript yanıtı: {transcription_result}"
            log_manager.add_log("ERROR", error_msg, job_id, {'video_num': video_num})
            raise RuntimeError(error_msg)

        # Transkript durumu loglama (sadece durum değiştiğinde veya her 10. kontrolde)
        status = transcription_result['status']
        status_check_count += 1
        
        if status != last_status or status_check_count % 10 == 0:
            log_manager.add_log("INFO", f"Transkript durumu: {status}", job_id, {
                'video_num': video_num,
                'transcript_status': status,
                'check_count': status_check_count
            })
            last_status = status

        if transcription_result['status'] == 'completed':
            words = transcription_result["words"]
            word_count = len(words)
            video_duration = words[-1]['end'] / 1000.0 if words else 0
            
            log_manager.add_log("SUCCESS", f"Transkript tamamlandı", job_id, {
                'video_num': video_num,
                'word_count': word_count,
                'duration_seconds': round(video_duration, 2)
            })
            
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
            
            segment_count = len(segments_to_keep)
            log_manager.add_log("SUCCESS", f"Sessizlik tespiti tamamlandı: {segment_count} segment bulundu", job_id, {
                'video_num': video_num,
                'segment_count': segment_count
            })
            
            # FFmpeg ile video kesme
            if segments_to_keep:
                log_manager.add_log("INFO", "FFmpeg kesme işlemi başladı", job_id, {
                    'video_num': video_num,
                    'segment_count': segment_count
                })
                
                ffmpeg_start_time = time.time()
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
                    error_msg = f"FFmpeg hatası: {result.stderr}"
                    log_manager.add_log("ERROR", error_msg, job_id, {'video_num': video_num})
                    raise RuntimeError(error_msg)
                
                ffmpeg_duration = int((time.time() - ffmpeg_start_time) * 1000)
                log_manager.add_log("SUCCESS", f"FFmpeg kesme işlemi tamamlandı", job_id, {
                    'video_num': video_num,
                    'duration_ms': ffmpeg_duration
                })
                
                total_duration = int((time.time() - step_start_time) * 1000)
                log_manager.add_log("INFO", f"Video işleme adımı tamamlandı", job_id, {
                    'video_num': video_num,
                    'total_duration_ms': total_duration
                })
                
                return True

        elif transcription_result['status'] == 'error':
            error_msg = transcription_result.get('error', 'Bilinmeyen hata')
            log_manager.add_log("ERROR", f"Transkript hatası: {error_msg}", job_id, {'video_num': video_num})
            raise RuntimeError(f"Transkript hatası: {error_msg}")
        
        elif transcription_result['status'] == 'processing':
            time.sleep(3)
        else:
            time.sleep(3)

def concatenate_videos(video_paths, output_path, job_id=None):
    """Birden fazla videoyu FFmpeg ile birleştirir"""
    if not video_paths:
        raise ValueError("Birleştirilecek video dosyası bulunamadı")
    
    concat_start_time = time.time()
    log_manager.add_log("INFO", f"Video birleştirme işlemi başladı: {len(video_paths)} video", job_id, {
        'video_count': len(video_paths)
    })
    
    # Geçici dosya listesi oluştur
    list_file_path = os.path.join(tempfile.gettempdir(), f"concat_list_{uuid.uuid4().hex}.txt")
    
    try:
        # FFmpeg concat için dosya listesi oluştur
        with open(list_file_path, 'w', encoding='utf-8') as f:
            for video_path in video_paths:
                if not os.path.exists(video_path):
                    error_msg = f"Video dosyası bulunamadı: {video_path}"
                    log_manager.add_log("ERROR", error_msg, job_id)
                    raise FileNotFoundError(error_msg)
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
            error_msg = f"Video birleştirme hatası: {result.stderr}"
            log_manager.add_log("ERROR", error_msg, job_id)
            raise RuntimeError(error_msg)
        
        concat_duration = int((time.time() - concat_start_time) * 1000)
        final_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        
        log_manager.add_log("SUCCESS", f"Video birleştirme tamamlandı: {output_path}", job_id, {
            'output_path': output_path,
            'file_size_bytes': final_size,
            'file_size_mb': round(final_size / (1024 * 1024), 2),
            'duration_ms': concat_duration
        })
        
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
            "/health": "Sağlık kontrolü (FFmpeg, API key durumu)",
            "/process": "Çoklu video işleme ve birleştirme (POST) - videos field'ı ile birden fazla video gönderilebilir",
            "/logs": "Tüm log mesajlarını getir (GET)",
            "/logs/<job_id>": "Belirli bir job'ın log mesajlarını getir (GET)",
            "/status/<job_id>": "Belirli bir job'ın durumunu getir (GET)"
        }
    })

@app.route('/health')
def health():
    """Geliştirilmiş sağlık kontrolü endpoint'i"""
    return jsonify({
        "status": "healthy",
        "ffmpeg_available": ffmpeg_available,
        "api_key_available": api_key_available,
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    })

@app.route('/process', methods=['POST'])
def process():
    """Çoklu video işleme ve birleştirme endpoint'i - Kaç video yüklenirse yüklensin işler"""
    job_start_time = time.time()
    job_id = str(uuid.uuid4())
    
    # Job başlatıldı
    log_manager.update_job_status(job_id, "pending", {
        'created_at': datetime.utcnow().isoformat() + 'Z'
    })
    log_manager.add_log("INFO", f"İşlem başlatıldı (job_id: {job_id})", job_id)
    
    try:
        # Hem 'videos' (yeni format) hem 'video' (eski format) desteği
        if 'videos' in request.files:
            files = request.files.getlist('videos')
        elif 'video' in request.files:
            # Eski format desteği - tek video'yu liste olarak al
            files = [request.files['video']]
        else:
            error_msg = "Video dosyaları bulunamadı. 'videos' field'ı ile video gönderin."
            log_manager.add_log("ERROR", error_msg, job_id)
            log_manager.update_job_status(job_id, "error", {'error': error_msg})
            return jsonify({"error": error_msg, "job_id": job_id}), 400
        
        if not files or len(files) == 0:
            error_msg = "Dosya seçilmedi"
            log_manager.add_log("ERROR", error_msg, job_id)
            log_manager.update_job_status(job_id, "error", {'error': error_msg})
            return jsonify({"error": error_msg, "job_id": job_id}), 400
        
        # Dosya sayısı bilgisi
        valid_files = [f for f in files if f.filename != '']
        file_count = len(valid_files)
        
        log_manager.add_log("INFO", f"Dosya sayısı bilgisi: {file_count} video işlenecek", job_id, {
            'file_count': file_count
        })
        log_manager.update_job_status(job_id, "processing", {
            'file_count': file_count,
            'status': 'processing'
        })
        
        if len(valid_files) == 0:
            error_msg = "Geçerli video dosyası bulunamadı"
            log_manager.add_log("ERROR", error_msg, job_id)
            log_manager.update_job_status(job_id, "error", {'error': error_msg})
            return jsonify({"error": error_msg, "job_id": job_id}), 400
        
        # outputvideo klasörünü oluştur
        output_dir = "outputvideo"
        os.makedirs(output_dir, exist_ok=True)
        
        # Geçici dosya yolları
        temp_inputs = []
        temp_outputs = []
        
        # Dosyaları kaydet ve işle
        for idx, file in enumerate(valid_files, start=1):
            file_id = str(uuid.uuid4())
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"input_{file_id}.mp4")
            
            # Dosya yükleme başladı
            file_size = 0
            if hasattr(file, 'content_length') and file.content_length:
                file_size = file.content_length
            else:
                # Dosyayı kaydet ve boyutunu al
                file.save(input_path)
                file_size = os.path.getsize(input_path)
            
            log_manager.add_log("INFO", f"Dosya yükleme başladı: {file.filename}", job_id, {
                'video_num': idx,
                'video_name': file.filename,
                'file_size_bytes': file_size,
                'file_size_mb': round(file_size / (1024 * 1024), 2)
            })
            
            if not os.path.exists(input_path):
                file.save(input_path)
            
            temp_inputs.append(input_path)
            
            output_filename = f"output_{idx}.mp4"
            output_path = os.path.join(output_dir, output_filename)
            temp_outputs.append(output_path)
            
            # Video işleme başladı
            log_manager.add_log("INFO", f"Video işleme başladı: {file.filename}", job_id, {
                'video_num': idx,
                'video_name': file.filename
            })
            
            # Video işle
            process_video(input_path, output_path, job_id, idx, file.filename)
        
        # Videoları birleştir
        if len(temp_outputs) > 1:
            log_manager.add_log("INFO", f"{len(temp_outputs)} video birleştiriliyor...", job_id, {
                'video_count': len(temp_outputs)
            })
            final_output_path = os.path.join(output_dir, "final_output.mp4")
            concatenate_videos(temp_outputs, final_output_path, job_id)
        else:
            # Tek video varsa, final_output olarak kopyala
            log_manager.add_log("INFO", "Tek video işlendi, birleştirme atlandı", job_id)
            final_output_path = os.path.join(output_dir, "final_output.mp4")
            import shutil
            copy_start_time = time.time()
            shutil.copy2(temp_outputs[0], final_output_path)
            copy_duration = int((time.time() - copy_start_time) * 1000)
            log_manager.add_log("SUCCESS", f"Video kopyalandı: {final_output_path}", job_id, {
                'duration_ms': copy_duration
            })
        
        # Final video hazır
        final_size = os.path.getsize(final_output_path)
        total_duration = int((time.time() - job_start_time) * 1000)
        
        log_manager.add_log("SUCCESS", f"Final video hazır: {final_output_path}", job_id, {
            'output_path': final_output_path,
            'file_size_bytes': final_size,
            'file_size_mb': round(final_size / (1024 * 1024), 2),
            'total_duration_ms': total_duration
        })
        log_manager.update_job_status(job_id, "completed", {
            'output_path': final_output_path,
            'file_size_bytes': final_size,
            'file_size_mb': round(final_size / (1024 * 1024), 2),
            'total_duration_ms': total_duration,
            'completed_at': datetime.utcnow().isoformat() + 'Z'
        })
        
        # Final videoyu gönder
        return send_file(
            final_output_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name="final_output.mp4"
        )
    
    except Exception as e:
        error_msg = str(e)
        log_manager.add_log("ERROR", f"İşlem hatası: {error_msg}", job_id)
        log_manager.update_job_status(job_id, "error", {
            'error': error_msg,
            'error_at': datetime.utcnow().isoformat() + 'Z'
        })
        return jsonify({"error": error_msg, "job_id": job_id}), 500
    
    finally:
        # Geçici dosyaları temizle
        for path in temp_inputs:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass

# ============================================================================
# LOG VE STATUS API ENDPOINT'LERİ
# ============================================================================

@app.route('/logs', methods=['GET'])
def get_logs():
    """Tüm log mesajlarını getir"""
    limit = request.args.get('limit', 100, type=int)
    job_id = request.args.get('job_id', None)
    
    logs = log_manager.get_logs(job_id=job_id, limit=limit)
    return jsonify({
        'logs': logs,
        'count': len(logs),
        'job_id': job_id
    })

@app.route('/logs/<job_id>', methods=['GET'])
def get_job_logs(job_id):
    """Belirli bir job'ın log mesajlarını getir"""
    limit = request.args.get('limit', 500, type=int)
    logs = log_manager.get_logs(job_id=job_id, limit=limit)
    
    if not logs:
        return jsonify({
            'error': f'Job ID bulunamadı: {job_id}',
            'logs': [],
            'count': 0
        }), 404
    
    return jsonify({
        'job_id': job_id,
        'logs': logs,
        'count': len(logs)
    })

@app.route('/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Belirli bir job'ın durumunu getir"""
    status = log_manager.get_job_status(job_id)
    
    if not status:
        return jsonify({
            'error': f'Job ID bulunamadı: {job_id}'
        }), 404
    
    # Son log mesajlarını da ekle
    recent_logs = log_manager.get_logs(job_id=job_id, limit=10)
    
    return jsonify({
        'job_id': job_id,
        'status': status,
        'recent_logs': recent_logs
    })

@app.route('/status', methods=['GET'])
def get_all_jobs():
    """Tüm job'ları listele"""
    jobs = log_manager.get_all_jobs()
    return jsonify({
        'jobs': jobs,
        'count': len(jobs)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    log_manager.add_log("INFO", f"Uygulama başlatıldı - Port: {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

