"""Çok dilli destek (i18n) — Türkçe ve İngilizce.

Bu modül tüm kullanıcı arayüzü metinlerini, hata mesajlarını ve
bildirim metinlerini merkezi olarak yönetir.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict


class Language(Enum):
    """Desteklenen diller."""

    TR = ("tr", "Türkçe")
    EN = ("en", "English")

    def __init__(self, code: str, display_name: str) -> None:
        self.code = code
        self.display_name = display_name


# ── Çeviri Sözlüğü ──────────────────────────────────────────────────────────

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # ── Başlık ve Genel ──
    "app_title": {
        "tr": "Audio Sync Tool",
        "en": "Audio Sync Tool",
    },
    "app_subtitle": {
        "tr": "Sağlam gecikme tespiti & senkronizasyon",
        "en": "Robust delay detection & synchronization",
    },

    # ── Drop Zone ──
    "source_audio": {
        "tr": "KAYNAK SES  (referans)",
        "en": "SOURCE AUDIO  (reference)",
    },
    "sync_audio": {
        "tr": "SENKRONİZE EDİLECEK SES",
        "en": "AUDIO TO SYNCHRONIZE",
    },
    "no_file_selected": {
        "tr": "— dosya seçilmedi —",
        "en": "— no file selected —",
    },
    "select_file": {
        "tr": "DOSYA SEÇ",
        "en": "SELECT FILE",
    },
    "audio_files": {
        "tr": "Ses Dosyaları",
        "en": "Audio Files",
    },
    "all_files": {
        "tr": "Tüm Dosyalar",
        "en": "All Files",
    },

    # ── Tespit Ayarları ──
    "detection_settings": {
        "tr": "TESPİT AYARLARI",
        "en": "DETECTION SETTINGS",
    },
    "skip_intro_sec": {
        "tr": "İLK FARKLI KISMI ATLA (sn)",
        "en": "SKIP INTRO SECTION (sec)",
    },
    "scan_window_count": {
        "tr": "TARAMA PENCERESİ SAYISI",
        "en": "SCAN WINDOW COUNT",
    },
    "force_48k": {
        "tr": "Her durumda çıktıyı 48 kHz'e zorla",
        "en": "Always force output to 48 kHz",
    },
    "force_48k_note": {
        "tr": "Not: Zorla kapalıysa yalnızca girişlerden biri 48 kHz değilse 48 kHz'e çevirir.",
        "en": "Note: If disabled, converts to 48 kHz only when one input is not 48 kHz.",
    },

    # ── Senkronizasyon Modu ──
    "sync_mode": {
        "tr": "SENKRONİZASYON MODU",
        "en": "SYNCHRONIZATION MODE",
    },
    "sync_mode_label": {
        "tr": "MOD",
        "en": "MODE",
    },
    "sync_mode_note": {
        "tr": "Not: Varsayılan mod (adelay / atrim) çoğu durum için en uygun seçimdir.",
        "en": "Note: Default mode (adelay / atrim) is the best choice for most cases.",
    },

    # ── FPS Dönüşümü ──
    "fps_conversion": {
        "tr": "FPS DÖNÜŞÜMÜ",
        "en": "FPS CONVERSION",
    },
    "fps_enable": {
        "tr": "Senkronizasyon öncesi FPS dönüşümü uygula",
        "en": "Apply FPS conversion before synchronization",
    },
    "fps_conversion_label": {
        "tr": "DÖNÜŞÜM",
        "en": "CONVERSION",
    },
    "fps_note": {
        "tr": "Not: Hedef sesin frame rate'i dönüştürülür,\nardından senkronizasyon bu ses üzerinde yapılır.",
        "en": "Note: Target audio frame rate is converted,\nthen synchronization is performed on this audio.",
    },
    "fps_slowdown": {
        "tr": "yavaşlatma",
        "en": "slowdown",
    },
    "fps_speedup": {
        "tr": "hızlandırma",
        "en": "speedup",
    },

    # ── Deew Encoding ──
    "deew_encoding": {
        "tr": "DEEW ENCODING",
        "en": "DEEW ENCODING",
    },
    "deew_enable": {
        "tr": "Senkronizasyon sonrası AC3/EAC3'e dönüştür",
        "en": "Convert to AC3/EAC3 after synchronization",
    },
    "encoder_label": {
        "tr": "ENCODER",
        "en": "ENCODER",
    },
    "format_label": {
        "tr": "FORMAT",
        "en": "FORMAT",
    },
    "channel_layout": {
        "tr": "KANAL DÜZENİ",
        "en": "CHANNEL LAYOUT",
    },
    "bitrate_label": {
        "tr": "BITRATE (kbps)",
        "en": "BITRATE (kbps)",
    },
    "drc_profile": {
        "tr": "DRC PROFİLİ",
        "en": "DRC PROFILE",
    },
    "dialnorm_label": {
        "tr": "DIALNORM (-31..0)",
        "en": "DIALNORM (-31..0)",
    },
    "delete_intermediate_wav": {
        "tr": "Dönüştürme sonrası ara WAV dosyasını sil",
        "en": "Delete intermediate WAV file after conversion",
    },
    "deew_ready": {
        "tr": "Deew ● hazır",
        "en": "Deew ● ready",
    },
    "deew_not_installed": {
        "tr": "Deew ● kurulu değil",
        "en": "Deew ● not installed",
    },
    "deew_unavailable": {
        "tr": "Deew ● kullanılamıyor",
        "en": "Deew ● unavailable",
    },
    "deew_desc": {
        "tr": "  → Deew ile AC3/EAC3 çıktı oluştur",
        "en": "  → Create AC3/EAC3 output with Deew",
    },
    "ffmpeg_enc_desc": {
        "tr": "  → FFmpeg dahili AC3/EAC3 encoder (ek araç gerektirmez)",
        "en": "  → FFmpeg built-in AC3/EAC3 encoder (no additional tools required)",
    },
    "deew_note": {
        "tr": "Not: Deew kurulu ve çalışır durumda olmalıdır.",
        "en": "Note: Deew must be installed and working.",
    },
    "ffmpeg_enc_note": {
        "tr": "Not: FFmpeg dahili encoder kullanılır, ek kurulum gerekmez.",
        "en": "Note: FFmpeg built-in encoder is used, no additional setup required.",
    },
    "default_bitrate": {
        "tr": "varsayılan",
        "en": "default",
    },

    # ── Bilgi Paneli ──
    "detected_delay": {
        "tr": "TESPİT EDİLEN KAYMA",
        "en": "DETECTED DELAY",
    },
    "channel": {
        "tr": "KANAL",
        "en": "CHANNEL",
    },
    "bit_depth": {
        "tr": "BIT DERİNLİĞİ",
        "en": "BIT DEPTH",
    },
    "output_sample_rate": {
        "tr": "ÇIKTI ÖRNEKLEME",
        "en": "OUTPUT SAMPLE RATE",
    },

    # ── Log ──
    "log_label": {
        "tr": "LOG",
        "en": "LOG",
    },

    # ── Butonlar ──
    "start_sync": {
        "tr": "⚡  SENKRONİZASYONU BAŞLAT",
        "en": "⚡  START SYNCHRONIZATION",
    },
    "processing": {
        "tr": "İşleniyor…",
        "en": "Processing…",
    },
    "canceling": {
        "tr": "İptal ediliyor…",
        "en": "Canceling…",
    },

    # ── Dil Seçimi ──
    "language": {
        "tr": "DİL",
        "en": "LANGUAGE",
    },

    # ── Mesajlar ──
    "missing_file_title": {
        "tr": "Eksik Dosya",
        "en": "Missing File",
    },
    "missing_file_msg": {
        "tr": "Lütfen her iki ses dosyasını da seçin.",
        "en": "Please select both audio files.",
    },
    "ffmpeg_not_found_title": {
        "tr": "FFmpeg Bulunamadı",
        "en": "FFmpeg Not Found",
    },
    "deew_not_found_title": {
        "tr": "Deew Bulunamadı",
        "en": "Deew Not Found",
    },
    "file_error_title": {
        "tr": "Dosya Hatası",
        "en": "File Error",
    },
    "save_output_title": {
        "tr": "Çıktıyı kaydet",
        "en": "Save output",
    },
    "success_title": {
        "tr": "Başarılı",
        "en": "Success",
    },
    "error_title": {
        "tr": "Hata",
        "en": "Error",
    },
    "file_saved_msg": {
        "tr": "Dosya kaydedildi:\n{path}",
        "en": "File saved:\n{path}",
    },

    # ── Log Mesajları ──
    "log_source": {
        "tr": "Kaynak: {name}",
        "en": "Source: {name}",
    },
    "log_sync_file": {
        "tr": "Senkronize: {name}",
        "en": "Sync: {name}",
    },
    "log_reading_info": {
        "tr": "Ses bilgileri okunuyor…",
        "en": "Reading audio information…",
    },
    "log_fps_applying": {
        "tr": "FPS dönüşümü uygulanıyor: {name}",
        "en": "Applying FPS conversion: {name}",
    },
    "log_fps_done": {
        "tr": "FPS dönüşümü tamamlandı, dönüştürülmüş ses kullanılacak.",
        "en": "FPS conversion completed, converted audio will be used.",
    },
    "log_preparing_mono": {
        "tr": "Analiz için tek kanallı ses akışı hazırlanıyor…",
        "en": "Preparing mono analysis audio…",
    },
    "log_analyzing": {
        "tr": "Sağlam senkron analizi yapılıyor…",
        "en": "Performing robust sync analysis…",
    },
    "log_applying_sync": {
        "tr": "FFmpeg ile senkronizasyon uygulanıyor…",
        "en": "Applying synchronization with FFmpeg…",
    },
    "log_timing": {
        "tr": "Süre: {step} ({seconds:.2f} sn)",
        "en": "Timing: {step} ({seconds:.2f}s)",
    },
    "log_command": {
        "tr": "Komut: {cmd}",
        "en": "Command: {cmd}",
    },
    "log_src_sr": {
        "tr": "Kaynak örnekleme: {src_sr} Hz  |  Senkron örnekleme: {sync_sr} Hz",
        "en": "Source sample rate: {src_sr} Hz  |  Sync sample rate: {sync_sr} Hz",
    },
    "log_output_info": {
        "tr": "Çıktı kanalı: {ch}ch  |  Bit: {bits}  |  Codec: {codec}",
        "en": "Output channel: {ch}ch  |  Bit: {bits}  |  Codec: {codec}",
    },
    "log_output_sr": {
        "tr": "Çıktı örnekleme: {label}",
        "en": "Output sample rate: {label}",
    },
    "log_detection_params": {
        "tr": "Tespit: ilk {skip:.0f} sn atla  |  pencere sayısı: {segments}",
        "en": "Detection: skip first {skip:.0f} sec  |  window count: {segments}",
    },
    "log_coarse_delay": {
        "tr": "Kaba kayma: {ms:+.1f} ms",
        "en": "Coarse delay: {ms:+.1f} ms",
    },
    "log_validation": {
        "tr": "Doğrulanan pencere: {used}/{total}  |  güven: {conf:.2f}",
        "en": "Validated windows: {used}/{total}  |  confidence: {conf:.2f}",
    },
    "log_skip_fallback": {
        "tr": "Uyarı: Seçilen atlama süresi çok uzun olduğu için analiz tam dosyada yapıldı.",
        "en": "Warning: Skip duration too long, analysis performed on full file.",
    },
    "log_drift": {
        "tr": "Tahmini drift: {drift:+.1f} ms/dk",
        "en": "Estimated drift: {drift:+.1f} ms/min",
    },
    "log_drift_warning": {
        "tr": "Uyarı: Kaynaklarda zaman içinde kayma var; tek delay tam kusursuz olmayabilir.",
        "en": "Warning: Sources have time drift; single delay may not be perfectly accurate.",
    },
    "log_final_delay": {
        "tr": "Nihai kayma: {ms:+.1f} ms  [{relation}]",
        "en": "Final delay: {ms:+.1f} ms  [{relation}]",
    },
    "log_completed": {
        "tr": "✓ Tamamlandı → {name}",
        "en": "✓ Completed → {name}",
    },
    "log_error": {
        "tr": "✗ Hata: {err}",
        "en": "✗ Error: {err}",
    },
    "log_cancel_requested": {
        "tr": "İptal isteği alındı, mevcut adım güvenli şekilde durdurulacak.",
        "en": "Cancel requested, the current step will stop safely.",
    },
    "log_cancelled": {
        "tr": "İşlem kullanıcı tarafından iptal edildi.",
        "en": "Operation cancelled by user.",
    },
    "log_sync_mode": {
        "tr": "Senkronizasyon modu: {mode}",
        "en": "Synchronization mode: {mode}",
    },

    # ── Deew Encoding Log ──
    "log_ffmpeg_deew_start": {
        "tr": "FFmpeg ile Deew çıktısı için encode başlıyor…",
        "en": "Starting FFmpeg encode for Deew output…",
    },
    "log_deew_info": {
        "tr": "Format: {fmt}  |  Bitrate: {br} kbps  |  Kanal: {ch}  |  Encoder: {enc}",
        "en": "Format: {fmt}  |  Bitrate: {br} kbps  |  Channel: {ch}  |  Encoder: {enc}",
    },
    "log_ffmpeg_deew_done": {
        "tr": "✓ FFmpeg encode tamamlandı → {name}",
        "en": "✓ FFmpeg encode completed → {name}",
    },
    "log_intermediate_wav_deleted": {
        "tr": "Ara WAV dosyası silindi.",
        "en": "Intermediate WAV file deleted.",
    },
    "log_intermediate_wav_delete_fail": {
        "tr": "Uyarı: Ara WAV dosyası silinemedi.",
        "en": "Warning: Could not delete intermediate WAV file.",
    },
    "log_ffmpeg_enc_error": {
        "tr": "✗ FFmpeg encoding hatası: {err}",
        "en": "✗ FFmpeg encoding error: {err}",
    },
    "log_wav_preserved": {
        "tr": "WAV dosyası korundu: {name}",
        "en": "WAV file preserved: {name}",
    },
    "log_deew_start": {
        "tr": "Deew ile encoding başlıyor…",
        "en": "Starting encoding with Deew…",
    },
    "log_deew_done": {
        "tr": "✓ Deew encoding tamamlandı → {name}",
        "en": "✓ Deew encoding completed → {name}",
    },
    "log_deew_error": {
        "tr": "✗ Deew hatası: {err}",
        "en": "✗ Deew error: {err}",
    },

    # ── Offset Açıklamaları ──
    "sync_ahead": {
        "tr": "sync ses ileride",
        "en": "sync audio is ahead",
    },
    "sync_behind": {
        "tr": "sync ses geride",
        "en": "sync audio is behind",
    },

    # ── Kanal Bilgisi ──
    "channel_info": {
        "tr": "{ch} kanal",
        "en": "{ch} channels",
    },
    "source_keep": {
        "tr": "kaynak",
        "en": "source",
    },
    "keep_source_sr": {
        "tr": "kaynağı koru (zaten 48 kHz)",
        "en": "keep source (already 48 kHz)",
    },

    # ── MKV / Container Stream Selection ──
    "mkv_select_title": {
        "tr": "Ses Akışı Seçimi",
        "en": "Audio Stream Selection",
    },
    "mkv_select_prompt": {
        "tr": "Bu dosyada birden fazla ses akışı bulundu.\nLütfen kullanmak istediğiniz akışı seçin:",
        "en": "Multiple audio streams found in this file.\nPlease select the stream you want to use:",
    },
    "mkv_stream_label": {
        "tr": "#{idx}: {codec} | {ch}ch | {rate}Hz | {lang}{title}",
        "en": "#{idx}: {codec} | {ch}ch | {rate}Hz | {lang}{title}",
    },
    "mkv_extracting": {
        "tr": "Ses akışı çıkarılıyor…",
        "en": "Extracting audio stream…",
    },
    "mkv_extracted": {
        "tr": "Ses akışı çıkarıldı: {name}",
        "en": "Audio stream extracted: {name}",
    },
    "mkv_no_audio": {
        "tr": "Bu dosyada ses akışı bulunamadı.",
        "en": "No audio streams found in this file.",
    },
    "mkv_extract_error": {
        "tr": "Ses akışı çıkarma hatası: {err}",
        "en": "Audio stream extraction error: {err}",
    },
    "mkv_single_stream": {
        "tr": "Tek ses akışı tespit edildi, otomatik seçildi.",
        "en": "Single audio stream detected, automatically selected.",
    },
    "log_mkv_detected": {
        "tr": "Container dosyası tespit edildi, ses akışları taranıyor…",
        "en": "Container file detected, scanning audio streams…",
    },

    # ── Drag & Drop ──
    "drop_hint": {
        "tr": "veya dosyayı buraya sürükleyin",
        "en": "or drag & drop file here",
    },
    "drop_hover": {
        "tr": "Dosyayı bırakın…",
        "en": "Drop file here…",
    },
    "container_files": {
        "tr": "Video/Container Dosyaları",
        "en": "Video/Container Files",
    },

    # ── Common Buttons ──
    "btn_ok": {
        "tr": "Tamam",
        "en": "OK",
    },
    "btn_cancel": {
        "tr": "İptal",
        "en": "Cancel",
    },

    # ── Analyze Only ──
    "analyze_only": {
        "tr": "🔍  SADECE ANALİZ ET",
        "en": "🔍  ANALYZE ONLY",
    },
    "analyzing": {
        "tr": "Analiz ediliyor…",
        "en": "Analyzing…",
    },
    "analyze_complete": {
        "tr": "Analiz tamamlandı.",
        "en": "Analysis complete.",
    },
    "analyze_result_header": {
        "tr": "═══════════ ANALİZ SONUÇLARI ═══════════",
        "en": "═══════════ ANALYSIS RESULTS ═══════════",
    },
    "sync_point_time": {
        "tr": "⏱  Senkron Noktası: {time}",
        "en": "⏱  Sync Point: {time}",
    },
    "delay_amount": {
        "tr": "📐  Gecikme Miktarı: {delay_ms:.2f} ms ({description})",
        "en": "📐  Delay Amount: {delay_ms:.2f} ms ({description})",
    },
    "confidence_score": {
        "tr": "📊  Güven Oranı: {confidence:.1f}",
        "en": "📊  Confidence Score: {confidence:.1f}",
    },
    "drift_amount": {
        "tr": "📈  Kayma Miktarı: {drift:.3f} ms/dk",
        "en": "📈  Drift Amount: {drift:.3f} ms/min",
    },
    "drift_none": {
        "tr": "📈  Kayma Miktarı: Tespit edilemedi",
        "en": "📈  Drift Amount: Not detected",
    },
    "coarse_delay": {
        "tr": "🔎  Kaba Analiz Gecikmesi: {coarse_ms:.2f} ms",
        "en": "🔎  Coarse Analysis Delay: {coarse_ms:.2f} ms",
    },
    "segments_used": {
        "tr": "📋  Kullanılan Segmentler: {used}/{total}",
        "en": "📋  Segments Used: {used}/{total}",
    },
    "analyze_no_files": {
        "tr": "Lütfen analiz için kaynak ve senkron dosyalarını seçin.",
        "en": "Please select source and sync files for analysis.",
    },
    "analyze_started": {
        "tr": "🔍 Senkronizasyon analizi başlatılıyor…",
        "en": "🔍 Starting synchronization analysis…",
    },
    "analyze_probing": {
        "tr": "📡 Dosya bilgileri okunuyor…",
        "en": "📡 Reading file information…",
    },
    "analyze_converting": {
        "tr": "🔄 Analiz için ses akışı hazırlanıyor…",
        "en": "🔄 Preparing analysis audio…",
    },
    "analyze_calculating": {
        "tr": "⚡ Gecikme hesaplanıyor…",
        "en": "⚡ Calculating delay…",
    },
    "analyze_src_info": {
        "tr": "📁 Kaynak: {channels}ch / {bits}bit / {sample_rate}Hz",
        "en": "📁 Source: {channels}ch / {bits}bit / {sample_rate}Hz",
    },
    "analyze_sync_info": {
        "tr": "📁 Senkron: {channels}ch / {bits}bit / {sample_rate}Hz",
        "en": "📁 Sync: {channels}ch / {bits}bit / {sample_rate}Hz",
    },
    "confidence_high": {
        "tr": "Yüksek",
        "en": "High",
    },
    "confidence_medium": {
        "tr": "Orta",
        "en": "Medium",
    },
    "confidence_low": {
        "tr": "Düşük",
        "en": "Low",
    },

    # ── Encoding Panel ──
    "encoding_pipeline": {
        "tr": "Çıktı Kodlama",
        "en": "Output Encoding",
    },
    "encoding_none": {
        "tr": "Kodlama Yok (Sadece Senkronize)",
        "en": "No Encoding (Sync Only)",
    },
    "encoding_deew": {
        "tr": "Deew (DD/DDP)",
        "en": "Deew (DD/DDP)",
    },
    "encoding_ffmpeg": {
        "tr": "FFmpeg (AAC/FLAC/Opus/AC3/EAC3)",
        "en": "FFmpeg (AAC/FLAC/Opus/AC3/EAC3)",
    },
    "encoding_qaac": {
        "tr": "qaac (AAC/M4A)",
        "en": "qaac (AAC/M4A)",
    },
    "encoding_format": {
        "tr": "Format",
        "en": "Format",
    },
    "encoding_bitrate": {
        "tr": "Bitrate (kbps)",
        "en": "Bitrate (kbps)",
    },
    "encoding_compression": {
        "tr": "Sıkıştırma Seviyesi",
        "en": "Compression Level",
    },
    "encoding_quality": {
        "tr": "Kalite",
        "en": "Quality",
    },
    "encoding_mode": {
        "tr": "Kodlama Modu",
        "en": "Encoding Mode",
    },
    "encoding_he_aac": {
        "tr": "HE-AAC Profili",
        "en": "HE-AAC Profile",
    },
    "encoding_no_delay": {
        "tr": "Gecikme Yok (--no-delay)",
        "en": "No Delay (--no-delay)",
    },
    "encoding_started": {
        "tr": "🔄 Kodlama başlatılıyor…",
        "en": "🔄 Starting encoding…",
    },
    "encoding_complete": {
        "tr": "✅ Kodlama tamamlandı: {summary}",
        "en": "✅ Encoding complete: {summary}",
    },
    "encoding_error": {
        "tr": "❌ Kodlama hatası: {error}",
        "en": "❌ Encoding error: {error}",
    },
    "qaac_not_found": {
        "tr": "qaac bulunamadı. Lütfen qaac'ı yükleyin ve PATH'e ekleyin (beklenen konum: C:\\qaac).",
        "en": "qaac not found. Please install qaac and add it to PATH (expected at C:\\qaac).",
    },
    "ffmpeg_aac_label": {
        "tr": "AAC (FFmpeg)",
        "en": "AAC (FFmpeg)",
    },
    "ffmpeg_flac_label": {
        "tr": "FLAC (FFmpeg)",
        "en": "FLAC (FFmpeg)",
    },
    "ffmpeg_opus_label": {
        "tr": "Opus (FFmpeg)",
        "en": "Opus (FFmpeg)",
    },
    "ffmpeg_ac3_label": {
        "tr": "AC3 (FFmpeg)",
        "en": "AC3 (FFmpeg)",
    },
    "ffmpeg_eac3_label": {
        "tr": "E-AC3 (FFmpeg)",
        "en": "E-AC3 (FFmpeg)",
    },
    "qaac_tvbr_label": {
        "tr": "True VBR (TVBR)",
        "en": "True VBR (TVBR)",
    },
    "qaac_cvbr_label": {
        "tr": "Constrained VBR (CVBR)",
        "en": "Constrained VBR (CVBR)",
    },
    "qaac_abr_label": {
        "tr": "ABR",
        "en": "ABR",
    },
    "qaac_cbr_label": {
        "tr": "CBR",
        "en": "CBR",
    },
    "encoding_pipeline_label": {
        "tr": "Kodlama Yöntemi",
        "en": "Encoding Pipeline",
    },
    "aac_bitrate_label": {
        "tr": "AAC Bitrate (kbps)",
        "en": "AAC Bitrate (kbps)",
    },
    "flac_compression_label": {
        "tr": "FLAC Sıkıştırma (0-8)",
        "en": "FLAC Compression (0-8)",
    },
    "opus_bitrate_label": {
        "tr": "Opus Bitrate (kbps)",
        "en": "Opus Bitrate (kbps)",
    },
    "ac3_bitrate_label": {
        "tr": "AC3 Bitrate (kbps)",
        "en": "AC3 Bitrate (kbps)",
    },
    "eac3_bitrate_label": {
        "tr": "E-AC3 Bitrate (kbps)",
        "en": "E-AC3 Bitrate (kbps)",
    },
    "qaac_quality_label": {
        "tr": "TVBR Kalite (0-127)",
        "en": "TVBR Quality (0-127)",
    },
    "ffmpeg_flac_compression_label": {
        "tr": "FLAC Sıkıştırma (0-12)",
        "en": "FLAC Compression (0-12)",
    },

    # ── FLAC Bit Depth & Pipeline Fixes ──
    "flac_bit_depth_label": {
        "tr": "FLAC Bit Derinliği",
        "en": "FLAC Bit Depth",
    },
    "flac_16bit": {
        "tr": "16-bit",
        "en": "16-bit",
    },
    "flac_24bit": {
        "tr": "24-bit",
        "en": "24-bit",
    },
    "intermediate_wav_cleanup": {
        "tr": "🗑️ Ara WAV dosyası silindi.",
        "en": "🗑️ Intermediate WAV file deleted.",
    },
    "sync_wav_output": {
        "tr": "📝 Senkron WAV çıktısı oluşturuldu.",
        "en": "📝 Sync WAV output created.",
    },

    # ── Tool Path Settings ──
    "tool_paths_title": {
        "tr": "Araç Yolları",
        "en": "Tool Paths",
    },
    "tool_paths_description": {
        "tr": "Harici araçlar için özel yollar belirleyin. Boş bırakılırsa sistem PATH'i kullanılır.",
        "en": "Set custom paths for external tools. Leave empty to use system PATH.",
    },
    "tool_path_ffmpeg": {
        "tr": "FFmpeg Yolu",
        "en": "FFmpeg Path",
    },
    "tool_path_ffprobe": {
        "tr": "FFprobe Yolu",
        "en": "FFprobe Path",
    },
    "tool_path_qaac": {
        "tr": "qaac Yolu",
        "en": "qaac Path",
    },
    "tool_path_deew": {
        "tr": "Deew Yolu",
        "en": "Deew Path",
    },
    "tool_path_browse": {
        "tr": "Gözat…",
        "en": "Browse…",
    },
    "tool_path_clear": {
        "tr": "Temizle",
        "en": "Clear",
    },
    "tool_path_using_path": {
        "tr": "Sistem PATH kullanılıyor",
        "en": "Using system PATH",
    },
    "tool_path_custom": {
        "tr": "Özel yol: {path}",
        "en": "Custom path: {path}",
    },
    "tool_path_not_found": {
        "tr": "⚠ Araç bulunamadı",
        "en": "⚠ Tool not found",
    },
    "tool_path_found": {
        "tr": "✓ Bulundu: {path}",
        "en": "✓ Found: {path}",
    },
    "tool_paths_saved": {
        "tr": "Araç yolları kaydedildi.",
        "en": "Tool paths saved.",
    },
    "tool_paths_button": {
        "tr": "⚙ Araç Yolları",
        "en": "⚙ Tool Paths",
    },
}


# ── Çeviri Yöneticisi ────────────────────────────────────────────────────────


class I18n:
    """Çeviri yöneticisi — aktif dile göre metin döndürür.

    Singleton pattern ile tek bir örnek kullanılır.

    Example::

        i18n = I18n()
        i18n.set_language(Language.EN)
        print(i18n.t("app_title"))  # "Audio Sync Tool"
    """

    _instance: I18n | None = None
    _language: Language = Language.EN

    def __new__(cls) -> I18n:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def language(self) -> Language:
        """Aktif dili döndürür."""
        return self._language

    def set_language(self, lang: Language) -> None:
        """Aktif dili değiştirir.

        Args:
            lang: Yeni dil.
        """
        self._language = lang

    def t(self, key: str, **kwargs: object) -> str:
        """Çeviri anahtarına göre metin döndürür.

        Args:
            key: Çeviri anahtarı.
            **kwargs: Format parametreleri.

        Returns:
            Çevrilmiş metin.  Anahtar bulunamazsa anahtar kendisi döner.
        """
        translations = TRANSLATIONS.get(key)
        if translations is None:
            return key

        text = translations.get(self._language.code, translations.get("tr", key))

        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                return text

        return text


# Singleton örneği
_i18n = I18n()


def get_i18n() -> I18n:
    """Singleton I18n örneğini döndürür."""
    return _i18n


def t(key: str, **kwargs: object) -> str:
    """Kısayol — aktif dile göre çeviri döndürür.

    Args:
        key: Çeviri anahtarı.
        **kwargs: Format parametreleri.

    Returns:
        Çevrilmiş metin.
    """
    return _i18n.t(key, **kwargs)
