#!/usr/bin/env python3
"""
Jumpcut API Test Script
Flask uygulamasını test etmek için kullanılır
"""

import requests
import json
import sys
import os
from pathlib import Path

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
    os.path.join(os.path.dirname(__file__), "inputvideo", "video7.mp4"),
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
        
        response = requests.post(f"{BASE_URL}/process", files=files, timeout=timeout_value)
        
        if response.status_code == 200:
            print_success(f"Status Code: {response.status_code}")
            
            # Output klasörü yoksa oluştur
            if not os.path.exists(OUTPUT_DIR):
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                print(f"Output klasörü oluşturuldu: {OUTPUT_DIR}")
            
            output_path = os.path.join(OUTPUT_DIR, "final_output.mp4")
            
            print(f"\nFinal video kaydediliyor: {output_path}")
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
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
                error_data = response.json()
                print(f"Hata detayı: {json.dumps(error_data, indent=2, ensure_ascii=False)}")
            except:
                print(f"Response: {response.text[:500]}")
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

