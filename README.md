# NetProbe

NetProbe, UDP uzerinde calisan reliable file transfer, traffic monitoring ve
network performance analiz platformudur. Proje; sequence number, ACK, timeout,
retransmission, duplicate packet kontrolu, SHA-256 integrity dogrulamasi,
deneysel loglama ve otomatik performans raporlama bilesenlerini icerir.

> GitHub baglantisi: Teslimden once kendi deponuzun URL'sini buraya ekleyin.

## Proje Yapisi

```text
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
  build_report_pdf.py    Markdown raporu PDF'e donusturme
reports/
  NetProbe_Rapor.md      Yaklasik 10 sayfalik teknik rapor
  NetProbe_Rapor.pdf     Uretilen PDF rapor
  figures/               Deney grafikleri
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

Bir terminalde server'i baslatin:

```powershell
python -m netprobe.server --host 127.0.0.1 --port 9000 --output-dir received
```

Baska bir terminalde client ile dosya gonderin:

```powershell
python -m netprobe.client data\samples\sample_128kb.bin --host 127.0.0.1 --port 9000 --chunk-size 1024 --timeout 0.2 --window-size 8
```

Server dosyayi `received/` klasorune yazar. Client ve server olaylari `logs/`
altinda JSONL olarak tutulur.

## Deneyleri Calistirma

Asagidaki komut packet boyutu, timeout, loss orani ve dosya boyutu senaryolarini
otomatik calistirir:

```powershell
python scripts\run_experiments.py
```

Deneylerden sonra grafikler ve dogrudan PDF raporu uretmek icin:

```powershell
python scripts\analyze_results.py
python scripts\build_direct_pdf.py
```

## Teslim Zip'i

Deney ve rapor uretildikten sonra proje kokunden:

```powershell
Compress-Archive -Path README.md,requirements.txt,netprobe,scripts,reports,data,logs,results,received -DestinationPath NetProbe_Teslim.zip -Force
```

## Varsayilan Protokol Parametreleri

- `max_retries`: 5 retransmission
- `window_size`: 8 packet
- `timeout`: 0.2 saniye
- `chunk_size`: 1024 byte
- `integrity`: SHA-256

Maksimum retransmission sayisina ragmen ACK alinmayan packet icin aktarim
basarisiz sayilir ve bu durum hem kullaniciya hem log dosyasina yazilir.
