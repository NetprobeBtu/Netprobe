from netprobe.server import ReliableUDPServer

def main():
    server = ReliableUDPServer(
        host="127.0.0.1",
        port=9000,
        output_dir="received",
        log_path="logs/server_events.jsonl",
        loss_rate=0.0,
        delay_ms=0.0,
    )
    
    print("=" * 50)
    print("   NETPROBE SUNUCUSU BAŞLATILDI (127.0.0.1:9000)")
    print("=" * 50)
    print("> Zaman aşımı (idle timeout) deaktive edildi.")
    print("> Sunucu siz kapatana kadar arka planda sürekli dinlemede kalacak.")
    print("> İstemcilerden gelen tüm dosyalar 'received/' klasörüne kaydedilecek.")
    print("> Sunucuyu durdurmak için CTRL+C tuşlarına basabilirsiniz.\n")
    
    try:
        # idle_timeout=None vererek 30 saniye sonra kapanma sorununun önüne geçiyoruz
        server.serve_forever(idle_timeout=None)
    except KeyboardInterrupt:
        server.stop()
        print("\n\n[!] Sunucu güvenli bir şekilde kapatıldı.")

if __name__ == "__main__":
    main()
