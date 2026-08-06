# Audio Sync Tool v2.5.0

The release that lets the tool say "I don't know". Every earlier version answered
every question, including the ones it had no business answering.

## What's New / Yenilikler

### The tool can now refuse

Cross-correlation always has a maximum, so a delay always comes out. Handed the
English audio of one film and the Turkish dub of another, the analyzer reported
**-1820320 ms** — a thirty-minute offset between two two-hour tracks — printed it
in the largest type on the screen and left the synchronize button enabled.

Every signal needed to catch it was already being computed and none was
consulted: the confidence sat at 1.87 where the noise floor is 1.0, the windows
contradicted each other, and the offset was a quarter of the runtime.

Every analysis now ends with a verdict — **reliable**, **doubtful** or **no
match**. A no match shows a dash instead of a number, lists what failed, and
stops the run before anything is written.

### Sample-accurate delays

The segment search works on a 20 ms feature grid, so its answer was quantised
before any averaging. A final band-limited GCC-PHAT pass over the raw audio
resolves 1/16000 s:

| Pair | Before | After | Ground truth |
|---|---|---|---|
| Two-hour cross-language pair | -10560 ms | **-10529.3 ms** | -10527 ms |
| Film spliced into three regions | one delay | **1496.8 / 1828.7 / 2165.1 ms** | 1497 / 1829 / 2165 |

Because that pass shares no code with the envelope correlation, agreement
between the two is also independent evidence that the answer is real.

### The written file is checked

Nothing verified the output before: every stage reported its intent and the run
ended with "completed" regardless of what came out. A few short probes now
measure the finished file against the reference it targeted.

```
✓  Verified: the written file sits +0.4 ms from the reference (6 probes).
```

### Also fixed

- The "windows disagree" warning read **0.0 ms** on a file whose offset stepped
  660 ms — the spread was measured against the candidate's own anchors instead
  of the offset that would be applied.
- A line fitted through a three-region staircase claimed 7.1 ms/min at R² 0.96.
- Anchors an hour apart and 670 ms adrift were interpolated linearly, giving
  every window in between an offset that was true nowhere in the film.

### Verified

- Six feature-length pairs from disc and streaming sources; ground truth from an
  independent per-window GCC-PHAT sweep sharing no code with the analyzer
- 228 tests, all nine CI jobs green

---

## Türkçe

Aracın "bilmiyorum" diyebildiği sürüm. Önceki her sürüm sorulan her soruya cevap
veriyordu — cevap vermemesi gereken sorulara da.

### Araç artık reddedebiliyor

Çapraz korelasyonun her zaman bir tepesi vardır, dolayısıyla her zaman bir
gecikme çıkar. Bir filmin İngilizce sesi ile başka bir filmin Türkçe dublajı
verildiğinde analizci **-1820320 ms** bildirdi — iki saatlik iki parça arasında
otuz dakikalık bir ofset — bunu ekrandaki en büyük puntoyla yazdı ve senkron
düğmesini açık bıraktı.

Bunu yakalamak için gereken her sinyal zaten hesaplanıyordu ve hiçbirine
bakılmıyordu: güven skoru, gürültü tabanının 1.0 olduğu yerde 1.87'de kalmıştı,
pencereler birbirini yalanlıyordu ve ofset toplam sürenin dörtte biriydi.

Artık her analiz bir kararla bitiyor — **güvenilir**, **şüpheli** ya da
**eşleşme yok**. Eşleşme yok durumunda sayı yerine bir tire gösterilir, neyin
tutmadığı sıralanır ve hiçbir şey yazılmadan çalışma durdurulur.

### Örnek hassasiyetinde gecikme

Segment araması 20 ms'lik bir öznitelik ızgarasında çalışır; cevabı herhangi bir
ortalama alınmadan önce yuvarlanıyordu. Ham ses üzerinde yapılan son bir bant
sınırlı GCC-PHAT geçişi 1/16000 s çözünürlük veriyor:

| Çift | Önce | Sonra | Gerçek değer |
|---|---|---|---|
| İki saatlik diller arası çift | -10560 ms | **-10529.3 ms** | -10527 ms |
| Üç bölgeye ayrılmış film | tek gecikme | **1496.8 / 1828.7 / 2165.1 ms** | 1497 / 1829 / 2165 |

Bu geçiş envelope korelasyonuyla hiç kod paylaşmadığı için, ikisinin uyuşması
aynı zamanda cevabın gerçek olduğuna dair bağımsız bir kanıttır.

### Yazılan dosya kontrol ediliyor

Daha önce çıktıyı hiçbir şey doğrulamıyordu: her aşama ne yapmak istediğini
bildiriyor, çalışma ne çıkarsa çıksın "tamamlandı" ile bitiyordu. Artık birkaç
kısa sonda, bitmiş dosyayı hedeflediği referansa karşı ölçüyor.

```
✓  Doğrulandı: yazılan dosya referansla +0.4 ms farkla hizalı (6 nokta).
```

### Ayrıca düzeltildi

- "Pencereler ayrışıyor" uyarısı, ofseti 660 ms sıçrayan bir dosyada **0.0 ms**
  okuyordu — saçılma, uygulanacak ofset yerine adayın kendi çıpalarına göre
  ölçülüyordu.
- Üç bölgeli bir merdivenden geçirilen doğru, R² 0.96 ile 7.1 ms/dk iddia etti.
- Bir saat arayla duran ve 670 ms ayrışan çıpalar doğrusal olarak
  birleştiriliyor, aradaki her pencereye filmin hiçbir yerinde doğru olmayan bir
  ofset dayatılıyordu.

### Doğrulandı

- Disk ve yayın kaynaklarından altı tam uzunlukta çift; referans değerler,
  analizciyle hiç kod paylaşmayan bağımsız bir pencere bazlı GCC-PHAT
  taramasından
- 228 test, dokuz CI işinin tamamı yeşil

---

Tam liste: [CHANGELOG.md](https://github.com/blast1see/AudioSyncTool/blob/main/CHANGELOG.md)
