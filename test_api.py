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
BASE_URL = os.getenv("API_URL", "https://jumpcut.onrender.com")

# Local test için:
# BASE_URL = "http://localhost:5000"

# Varsayılan video dosyası yolu
DEFAULT_VIDEO_PATH = os.path.join(os.path.dirname(__file__), "inputvideo", "video7.mp4")

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

def test_process_endpoint(video_path=None):
    """Video işleme endpoint'ini test et"""
    print_header("Video İşleme Testi (/process)")
    
    # Eğer video_path verilmemişse, varsayılan yolu kullan
    if not video_path:
        video_path = DEFAULT_VIDEO_PATH
    
    # Dosya yolunu normalize et (Windows için)
    video_path = os.path.normpath(video_path)
    
    if not os.path.exists(video_path):
        print_error(f"Video dosyası bulunamadı: {video_path}")
        print(f"Mutlak yol: {os.path.abspath(video_path)}")
        return False
    
    file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB
    print(f"Video dosyası: {video_path}")
    print(f"Dosya boyutu: {file_size:.2f} MB")
    
    try:
        with open(video_path, 'rb') as f:
            files = {'video': (os.path.basename(video_path), f, 'video/mp4')}
            print("\nVideo yükleniyor ve işleniyor... (Bu biraz zaman alabilir)")
            # Render.com için timeout'u artırdık (30 dakika)
            timeout_value = 120 if "render.com" in BASE_URL else 600
            print(f"Timeout: {timeout_value//60} dakika")
            response = requests.post(f"{BASE_URL}/process", files=files, timeout=timeout_value)
        
        if response.status_code == 200:
            print_success(f"Status Code: {response.status_code}")
            
            # İşlenmiş videoyu kaydet (outputvideo klasörüne)
            # Output klasörü yoksa oluştur
            if not os.path.exists(OUTPUT_DIR):
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                print(f"Output klasörü oluşturuldu: {OUTPUT_DIR}")
            
            output_filename = f"output_{os.path.basename(video_path)}"
            output_path = os.path.join(OUTPUT_DIR, output_filename)
            
            print(f"\nVideo kaydediliyor: {output_path}")
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            if os.path.exists(output_path):
                output_size = os.path.getsize(output_path) / (1024 * 1024)  # MB
                print_success(f"İşlenmiş video kaydedildi: {output_path}")
                print_success(f"Çıktı dosya boyutu: {output_size:.2f} MB")
            else:
                print_error(f"Dosya kaydedilemedi: {output_path}")
                return False
            return True
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
    
    # 3. Process endpoint testi
    # Komut satırından video yolu verilmişse kullan, yoksa varsayılan yolu kullan
    video_path = sys.argv[1] if len(sys.argv) > 1 else None
    results.append(("Video İşleme", test_process_endpoint(video_path)))
    
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

