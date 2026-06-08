# NetProbe

NetProbe, UDP uzerinde calisan reliable file transfer, traffic monitoring ve
network performance analiz platformudur. Proje; sequence number, ACK, timeout,
retransmission, duplicate packet kontrolu, SHA-256 integrity dogrulamasi,
deneysel loglama ve otomatik performans raporlama bilesenlerini icerir.

## Proje Yapisi

```text
start_server.py          Sunucuyu başlatmak için kullanılan ana script
test_32kb.py             32 KB dosya transfer testi
test_128kb.py            128 KB dosya transfer testi
test_384kb.py            384 KB dosya transfer testi
netprobe/
  client.py              UDP reliable transfer client
  server.py              UDP server ve yeniden birlestirme mantigi
  protocol.py            Application Layer packet formati ve checksum
  logger.py              JSONL event log sistemi
  metrics.py             Throughput, goodput, RTT ve oran hesaplari
  tcp_baseline.py        Opsiyonel TCP karsilastirma yardimcisi
scripts/
  run_experiments.py     En az 3 senaryo icin otomatik deney kosumu
  analyze_results.py     CSV sonuclardan SVG grafik uretimi
data/
  samples/               Deney icin uretilen ornek dosyalar
logs/                    Transfer event loglari
results/                 Ozet CSV/JSON deney sonuclari
received/                Server tarafinda yeniden olusturulan dosyalar
```

## Gereksinimler

- Python 3.10 veya uzeri
- Ek paket gerekmez; tum kod Python standart kutuphanesi ile yazilmistir.

## Tek Dosya Transferi

Bir terminalde (Sunucu) baslatin:

```powershell
python start_server.py
```

Baska bir terminalde (Testler) dosyalari gonderin:

```powershell
python test_32kb.py
python test_128kb.py
python test_384kb.py
```

Server dosyayi `received/` klasorune yazar. Client ve server olaylari `logs/`
altinda JSONL olarak tutulur.

## Deneyleri Calistirma

Asagidaki komut packet boyutu, timeout, loss orani ve dosya boyutu senaryolarini
otomatik calistirir:

```powershell
python scripts\run_experiments.py
```

Deneylerden sonra grafikleri uretmek icin:

```powershell
python scripts\analyze_results.py
```

## Varsayilan Protokol Parametreleri

- `max_retries`: 5 retransmission
- `window_size`: 8 packet
- `timeout`: 0.2 saniye
- `chunk_size`: 1024 byte
- `integrity`: SHA-256

Maksimum retransmission sayisina ragmen ACK alinmayan packet icin aktarim
basarisiz sayilir ve bu durum hem kullaniciya hem log dosyasina yazilir.
