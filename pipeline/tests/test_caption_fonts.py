from clipgauge_pipeline.captions import ass
from clipgauge_pipeline.captions.ass import Word


def test_all_caption_presets_ship_a_unicode_fallback_font():
    fallback = ass.FONTS_DIR / "NotoSansTamil-Regular.ttf"

    assert fallback.is_file()
    assert fallback.stat().st_size > 10_000
    assert all(preset.font_file for preset in ass.PRESETS.values())


def test_all_caption_presets_preserve_tamil_text_for_ffmpeg_fallback():
    words = [Word(text="வணக்கம்", start=0.0, end=0.8)]
    for preset_name in ass.PRESETS:
        rendered = ass.build_ass(words, [], preset_name=preset_name)
        assert "வணக்கம்" in rendered
        assert f"Style: Cap,{ass.PRESETS[preset_name].font}," in rendered
