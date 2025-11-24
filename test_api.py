#!/usr/bin/env python3
"""
Jumpcut API Test Script
Flask uygulamasını test etmek için kullanılır
"""

import requests
import json
import sys
import os
import time
import threading
from pathlib import Path
from datetime import datetime

# API base URL
# Render URL (production) veya local URL (development) kullanabilirsiniz
# Environment variable'dan al veya varsayılan kullan
BASE_URL = os.getenv("API_URL", "http://localhost:5000")

# Production test için:
# BASE_URL = "https://jumpcut.onrender.com"

# ============================================================================
# VİDEO INPUT KONFİGÜRASYONU
# ============================================================================
# İşlenecek video yolları - Kaç video tanımlarsanız o kadar işlem yapılır
# Minimum 1 video, maksimum sınır yok
VIDEO_PATHS = [
    os.path.join(os.path.dirname(__file__), "inputvideo", "video7.mp4")
    
]
# ============================================================================

# Output klasörü yolu
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputvideo")

def print_header(text):
    """Başlık yazdır"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)

def print_success(text):
    """Başarı mesajı"""
    print(f"✓ {text}")

def print_error(text):
    """Hata mesajı"""
    print(f"✗ {text}")

def print_log(log_entry):
    """Log mesajını formatlı şekilde yazdır"""
    level = log_entry.get('level', 'INFO')
    message = log_entry.get('message', '')
    timestamp = log_entry.get('timestamp', '')
    metadata = log_entry.get('metadata', {})
    
    # Level sembolleri
    level_symbols = {
        'INFO': 'ℹ️',
        'SUCCESS': '✅',
        'WARNING': '⚠️',
        'ERROR': '❌'
    }
    symbol = level_symbols.get(level, '•')
    
    # Konsol çıktısı formatla
    log_msg = f"[{timestamp}] {symbol} [{level}] {message}"
    
    # Metadata varsa ekle
    if metadata:
        metadata_strs = []
        for key, value in metadata.items():
            if key not in ['job_id']:
                metadata_strs.append(f"{key}={value}")
        if metadata_strs:
            log_msg += f" | {' | '.join(metadata_strs)}"
    
    print(log_msg)

def poll_logs(job_id, stop_event, base_url):
    """Belirli bir job'ın loglarını polling yaparak konsola yazdır"""
    last_log_count = 0
    
    while not stop_event.is_set():
        try:
            response = requests.get(f"{base_url}/logs/{job_id}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                logs = data.get('logs', [])
                
                # Yeni logları yazdır
                if len(logs) > last_log_count:
                    new_logs = logs[last_log_count:]
                    for log_entry in new_logs:
                        print_log(log_entry)
                    last_log_count = len(logs)
            
            time.sleep(2)  # 2 saniyede bir kontrol et
        except requests.exceptions.RequestException:
            # Bağlantı hatası durumunda sessizce devam et
            time.sleep(2)
        except Exception:
            # Diğer hataları görmezden gel
            time.sleep(2)

def test_root_endpoint():
    """Ana endpoint'i test et"""
    print_header("Ana Endpoint Testi (/)")
    try:
        response = requests.get(f"{BASE_URL}/")
        if response.status_code == 200:
            data = response.json()
            print_success(f"Status Code: {response.status_code}")
            print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
            return True
        else:
            print_error(f"Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except requests.exceptions.ConnectionError:
        print_error("Bağlantı hatası! Uygulama çalışıyor mu?")
        print(f"Lütfen {BASE_URL} adresinde uygulamanın çalıştığından emin olun.")
        return False
    except Exception as e:
        print_error(f"Beklenmeyen hata: {str(e)}")
        return False

def test_health_endpoint():
    """Health endpoint'ini test et"""
    print_header("Health Check Testi (/health)")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            data = response.json()
            print_success(f"Status Code: {response.status_code}")
            print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
            return True
        else:
            print_error(f"Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"Hata: {str(e)}")
        return False

def test_process_endpoint(video_paths=None):
    """Video işleme ve birleştirme endpoint'ini test et - Kaç video varsa o kadar işlem yapar"""
    print_header("Video İşleme Testi (/process)")
    
    # Eğer video_paths verilmemişse, varsayılan yolları kullan
    if not video_paths:
        video_paths = VIDEO_PATHS
    
    if not video_paths or len(video_paths) == 0:
        print_error("Video yolları listesi boş. VIDEO_PATHS dizisini doldurun.")
        return False
    
    # Video dosyalarını kontrol et
    valid_videos = []
    for video_path in video_paths:
        video_path = os.path.normpath(video_path)
        if not os.path.exists(video_path):
            print_error(f"Video dosyası bulunamadı: {video_path}")
            continue
        valid_videos.append(video_path)
        file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB
        print(f"  ✓ {os.path.basename(video_path)} ({file_size:.2f} MB)")
    
    if len(valid_videos) == 0:
        print_error("Geçerli video dosyası bulunamadı")
        return False
    
    if len(valid_videos) != len(video_paths):
        print(f"\nUyarı: {len(valid_videos)}/{len(video_paths)} video geçerli")
    
    # Dosya handle'larını saklamak için liste
    file_handles = []
    
    try:
        # Dosyaları hazırla - context manager ile aç
        files = []
        for video_path in valid_videos:
            file_handle = open(video_path, 'rb')
            file_handles.append(file_handle)
            # 'videos' field'ı ile gönder (çoğul - çoklu video desteği için)
            files.append(('videos', (os.path.basename(video_path), file_handle, 'video/mp4')))
        
        print(f"\n{len(valid_videos)} video yükleniyor ve işleniyor... (Bu uzun zaman alabilir)")
        print(f"Gönderilen dosya sayısı: {len(files)}")
        timeout_value = 1800 if "render.com" in BASE_URL else 600
        timeout_minutes = timeout_value // 60
        print(f"Timeout: {timeout_minutes} dakika ({timeout_value} saniye)")
        print(f"Endpoint: {BASE_URL}/process")
        print("\n" + "=" * 60)
        print("  LOG MESAJLARI")
        print("=" * 60 + "\n")
        
        # İşlem başlamadan önce mevcut job'ları al
        initial_jobs = {}
        try:
            status_response = requests.get(f"{BASE_URL}/status", timeout=5)
            if status_response.status_code == 200:
                jobs_data = status_response.json()
                initial_jobs = jobs_data.get('jobs', {})
        except:
            pass
        
        # Log polling için thread başlat
        stop_logging = threading.Event()
        log_thread = None
        job_id = None
        last_log_count = {'count': 0}  # Thread-safe için dict kullan
        
        def poll_logs_thread():
            """Arka planda log polling yap"""
            nonlocal job_id, last_log_count
            while not stop_logging.is_set() and job_id:
                try:
                    log_response = requests.get(f"{BASE_URL}/logs/{job_id}", timeout=5)
                    if log_response.status_code == 200:
                        logs_data = log_response.json()
                        logs = logs_data.get('logs', [])
                        
                        # Yeni logları yazdır
                        if len(logs) > last_log_count['count']:
                            new_logs = logs[last_log_count['count']:]
                            for log_entry in new_logs:
                                print_log(log_entry)
                            last_log_count['count'] = len(logs)
                    
                    time.sleep(2)  # 2 saniyede bir kontrol et
                except:
                    time.sleep(2)
        
        # İşlemi başlat (stream=False, normal blocking request)
        response = None
        
        try:
            # İşlemi başlat - bu uzun sürebilir
            response = requests.post(f"{BASE_URL}/process", files=files, timeout=timeout_value)
        except requests.exceptions.Timeout:
            stop_logging.set()
            print_error("İstek zaman aşımına uğradı. Video işleme çok uzun sürdü.")
            return False
        except Exception as e:
            stop_logging.set()
            print_error(f"Hata: {str(e)}")
            return False
        
        # Hata durumunda job_id'yi al ve logları göster
        if response.status_code != 200:
            stop_logging.set()
            try:
                error_data = response.json()
                job_id = error_data.get('job_id')
                if job_id:
                    print(f"\nJob ID: {job_id}")
                    print("Hata logları:\n")
                    log_response = requests.get(f"{BASE_URL}/logs/{job_id}")
                    if log_response.status_code == 200:
                        logs_data = log_response.json()
                        for log_entry in logs_data.get('logs', []):
                            print_log(log_entry)
            except:
                pass
            return False
        
        # Başarılı durumda - yeni job'ı bul ve loglarını göster
        try:
            time.sleep(0.5)  # Job oluşması için kısa bekleme
            
            status_response = requests.get(f"{BASE_URL}/status", timeout=5)
            if status_response.status_code == 200:
                jobs_data = status_response.json()
                current_jobs = jobs_data.get('jobs', {})
                
                # Yeni job'ı bul
                for jid in current_jobs:
                    if jid not in initial_jobs:
                        job_id = jid
                        break
                
                # Eğer yeni job bulunamadıysa, en son job'ı al
                if not job_id and current_jobs:
                    latest_job = None
                    latest_time = None
                    for jid, job_data in current_jobs.items():
                        created_at = job_data.get('created_at', '')
                        if latest_time is None or created_at > latest_time:
                            latest_time = created_at
                            latest_job = jid
                    job_id = latest_job
                
                # Job bulunduysa tüm loglarını göster
                if job_id:
                    log_response = requests.get(f"{BASE_URL}/logs/{job_id}")
                    if log_response.status_code == 200:
                        logs_data = log_response.json()
                        print(f"\nJob ID: {job_id}\n")
                        for log_entry in logs_data.get('logs', []):
                            print_log(log_entry)
        except Exception as e:
            # Log alma hatası durumunda devam et
            pass
        
        stop_logging.set()
        
        # Response içeriğini oku
        response_content = response.content
        
        if response.status_code == 200 and len(response_content) > 0:
            print_success(f"Status Code: {response.status_code}")
            
            # Output klasörü yoksa oluştur
            if not os.path.exists(OUTPUT_DIR):
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                print(f"\nOutput klasörü oluşturuldu: {OUTPUT_DIR}")
            
            output_path = os.path.join(OUTPUT_DIR, "final_output.mp4")
            
            print(f"\nFinal video kaydediliyor: {output_path}")
            with open(output_path, 'wb') as f:
                f.write(response_content)
            
            if os.path.exists(output_path):
                output_size = os.path.getsize(output_path) / (1024 * 1024)  # MB
                print_success(f"Final video kaydedildi: {output_path}")
                print_success(f"Final çıktı dosya boyutu: {output_size:.2f} MB")
                return True
            else:
                print_error(f"Dosya kaydedilemedi: {output_path}")
                return False
        else:
            print_error(f"Status Code: {response.status_code}")
            try:
                # JSON response olabilir (hata durumu)
                error_data = json.loads(response_content.decode('utf-8'))
                print(f"Hata detayı: {json.dumps(error_data, indent=2, ensure_ascii=False)}")
            except:
                print(f"Response: {response_content[:500].decode('utf-8', errors='ignore')}")
            return False
    except requests.exceptions.Timeout:
        print_error("İstek zaman aşımına uğradı. Video işleme çok uzun sürdü.")
        return False
    except Exception as e:
        print_error(f"Hata: {str(e)}")
        return False
    finally:
        # Dosya handle'larını kapat
        for file_handle in file_handles:
            try:
                file_handle.close()
            except:
                pass

def main():
    """Ana test fonksiyonu"""
    print("\n" + "=" * 60)
    print("  JUMPCUT API TEST SCRIPT")
    print("=" * 60)
    print(f"\nAPI URL: {BASE_URL}\n")
    
    results = []
    
    # 1. Root endpoint testi
    results.append(("Ana Endpoint", test_root_endpoint()))
    
    # 2. Health endpoint testi
    results.append(("Health Check", test_health_endpoint()))
    
    # 3. Process endpoint testi (çoklu video)
    # VIDEO_PATHS dizisinde kaç video varsa o kadar işlem yapılır
    if VIDEO_PATHS and isinstance(VIDEO_PATHS, list) and len(VIDEO_PATHS) > 0:
        results.append(("Video İşleme", test_process_endpoint()))
    else:
        print_error("VIDEO_PATHS dizisi boş! Lütfen test_api.py dosyasında VIDEO_PATHS dizisini doldurun.")
        results.append(("Video İşleme", False))
    
    # Sonuçları özetle
    print_header("Test Sonuçları")
    passed = sum(1 for _, result in results if result is True)
    total = sum(1 for _, result in results if result is not None)
    
    for name, result in results:
        if result is True:
            print_success(f"{name}: BAŞARILI")
        elif result is False:
            print_error(f"{name}: BAŞARISIZ")
        else:
            print(f"⊘ {name}: ATLANDI")
    
    print(f"\nToplam: {passed}/{total} test başarılı")
    
    if passed == total and total > 0:
        print("\n🎉 Tüm testler başarılı!")
        return 0
    else:
        print("\n⚠️  Bazı testler başarısız oldu.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

