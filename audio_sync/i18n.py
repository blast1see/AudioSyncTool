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
        "tr": "Not: Varsayılan mod (adelay+amix) çoğu durum için en uygun seçimdir.",
        "en": "Note: Default mode (adelay+amix) is the best choice for most cases.",
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

    # ── Dolby Encoding ──
    "dolby_encoding": {
        "tr": "DOLBY ENCODING",
        "en": "DOLBY ENCODING",
    },
    "dolby_enable": {
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
    "dee_ready": {
        "tr": "DEE ● hazır",
        "en": "DEE ● ready",
    },
    "dee_not_installed": {
        "tr": "DEE ● kurulu değil",
        "en": "DEE ● not installed",
    },
    "dee_desc": {
        "tr": "  → Dolby Encoding Engine (yüksek kalite, DEE gerektirir)",
        "en": "  → Dolby Encoding Engine (high quality, requires DEE)",
    },
    "ffmpeg_enc_desc": {
        "tr": "  → FFmpeg dahili AC3/EAC3 encoder (ek araç gerektirmez)",
        "en": "  → FFmpeg built-in AC3/EAC3 encoder (no additional tools required)",
    },
    "dee_note": {
        "tr": "Not: Deew, Dolby Encoding Engine (DEE) gerektirir.",
        "en": "Note: Deew requires Dolby Encoding Engine (DEE).",
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
        "tr": "Analiz için tek kanallı WAV hazırlanıyor…",
        "en": "Preparing mono WAV for analysis…",
    },
    "log_analyzing": {
        "tr": "Sağlam senkron analizi yapılıyor…",
        "en": "Performing robust sync analysis…",
    },
    "log_applying_sync": {
        "tr": "FFmpeg ile senkronizasyon uygulanıyor…",
        "en": "Applying synchronization with FFmpeg…",
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
    "log_sync_mode": {
        "tr": "Senkronizasyon modu: {mode}",
        "en": "Synchronization mode: {mode}",
    },

    # ── Dolby Encoding Log ──
    "log_ffmpeg_dolby_start": {
        "tr": "FFmpeg ile Dolby encoding başlıyor…",
        "en": "Starting Dolby encoding with FFmpeg…",
    },
    "log_dolby_info": {
        "tr": "Format: {fmt}  |  Bitrate: {br} kbps  |  Kanal: {ch}  |  Encoder: {enc}",
        "en": "Format: {fmt}  |  Bitrate: {br} kbps  |  Channel: {ch}  |  Encoder: {enc}",
    },
    "log_ffmpeg_dolby_done": {
        "tr": "✓ FFmpeg Dolby encoding tamamlandı → {name}",
        "en": "✓ FFmpeg Dolby encoding completed → {name}",
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
        "tr": "Deew ile Dolby encoding başlıyor…",
        "en": "Starting Dolby encoding with Deew…",
    },
    "log_deew_dolby_done": {
        "tr": "✓ Dolby encoding tamamlandı → {name}",
        "en": "✓ Dolby encoding completed → {name}",
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
    _language: Language = Language.TR

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
