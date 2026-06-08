import sys
from pathlib import Path
from netprobe.client import ReliableUDPClient

def main():
    client = ReliableUDPClient(
        host="127.0.0.1",
        port=9000,
        chunk_size=1024,
        timeout_seconds=0.2,
        max_retries=5,
        window_size=8,
        log_path="logs/client_events.jsonl",
    )
    file_path = Path("data/samples/sample_128kb.bin")
    if not file_path.exists():
        print(f"Hata: {file_path} bulunamadı!")
        sys.exit(1)
        
    print(f"--- 128 KB Dosya Aktarımı Başlıyor ---")
    result = client.send_file(file_path, label="test_128kb")
    
    print("\n--- Aktarım Sonucu ---")
    print("DURUM:", "BAŞARILI (OK)" if result.ok else "BAŞARISIZ (FAILED)")
    if result.ok:
        print(f"Geçen Süre: {result.metrics.completion_time_seconds} saniye")
        print(f"Throughput: {result.metrics.throughput_bps / 1_000_000:.3f} Mbps")
        print(f"Goodput: {result.metrics.goodput_bps / 1_000_000:.3f} Mbps")
        print(f"Gönderilen Paket Sayısı: {result.metrics.datagrams_sent}")
        print(f"Başarılı Paket (ACK) Sayısı: {result.metrics.ack_received}")

if __name__ == "__main__":
    main()
