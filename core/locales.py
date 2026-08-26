"""Suy ra ngon ngu trinh duyet tu quoc gia cua IP proxy.

Firefox lay ca header ``Accept-Language`` lan ``navigator.language(s)`` tu pref
``intl.accept_languages`` -- da do thuc te tren Firefox 154 -- nen chi can dat
dung pref nay la khop duoc ngon ngu, khong phai cai them goi ngon ngu nao.
"""

from __future__ import annotations

# Ma quoc gia -> the ngon ngu chinh. Chi liet ke nhung nuoc hay gap;
# nuoc khong co trong bang se dung "en-US".
COUNTRY_LANGUAGE = {
    "AE": "ar-AE", "AR": "es-AR", "AT": "de-AT", "AU": "en-AU", "BD": "bn-BD",
    "BE": "nl-BE", "BG": "bg-BG", "BH": "ar-BH", "BO": "es-BO", "BR": "pt-BR",
    "BY": "be-BY", "CA": "en-CA", "CH": "de-CH", "CL": "es-CL", "CN": "zh-CN",
    "CO": "es-CO", "CR": "es-CR", "CZ": "cs-CZ", "DE": "de-DE", "DK": "da-DK",
    "DO": "es-DO", "DZ": "ar-DZ", "EC": "es-EC", "EE": "et-EE", "EG": "ar-EG",
    "ES": "es-ES", "FI": "fi-FI", "FR": "fr-FR", "GB": "en-GB", "GR": "el-GR",
    "GT": "es-GT", "HK": "zh-HK", "HN": "es-HN", "HR": "hr-HR", "HU": "hu-HU",
    "ID": "id-ID", "IE": "en-IE", "IL": "he-IL", "IN": "en-IN", "IQ": "ar-IQ",
    "IR": "fa-IR", "IS": "is-IS", "IT": "it-IT", "JO": "ar-JO", "JP": "ja-JP",
    "KE": "en-KE", "KH": "km-KH", "KR": "ko-KR", "KW": "ar-KW", "KZ": "ru-KZ",
    "LB": "ar-LB", "LK": "si-LK", "LT": "lt-LT", "LU": "fr-LU", "LV": "lv-LV",
    "MA": "ar-MA", "MX": "es-MX", "MY": "ms-MY", "NG": "en-NG", "NL": "nl-NL",
    "NO": "nb-NO", "NP": "ne-NP", "NZ": "en-NZ", "OM": "ar-OM", "PA": "es-PA",
    "PE": "es-PE", "PH": "en-PH", "PK": "ur-PK", "PL": "pl-PL", "PR": "es-PR",
    "PT": "pt-PT", "PY": "es-PY", "QA": "ar-QA", "RO": "ro-RO", "RS": "sr-RS",
    "RU": "ru-RU", "SA": "ar-SA", "SE": "sv-SE", "SG": "en-SG", "SI": "sl-SI",
    "SK": "sk-SK", "TH": "th-TH", "TN": "ar-TN", "TR": "tr-TR", "TW": "zh-TW",
    "UA": "uk-UA", "US": "en-US", "UY": "es-UY", "VE": "es-VE", "VN": "vi-VN",
    "ZA": "en-ZA",
}

DEFAULT_LANGUAGE = "en-US"


def language_for(country: str) -> str:
    """The ngon ngu chinh cua mot ma quoc gia hai chu."""
    return COUNTRY_LANGUAGE.get((country or "").strip().upper(), DEFAULT_LANGUAGE)


def accept_languages(country: str) -> str:
    """Chuoi cho pref ``intl.accept_languages``.

    Vi du ``"DE"`` -> ``"de-DE, de, en-US, en"``: ngon ngu ban dia truoc, roi
    tieng Anh lam du phong -- giong cach da so trinh duyet that duoc cau hinh.
    """
    primary = language_for(country)
    base = primary.split("-")[0]

    ordered = [primary]
    if base != primary:
        ordered.append(base)
    for fallback in (DEFAULT_LANGUAGE, "en"):
        if fallback not in ordered:
            ordered.append(fallback)
    return ", ".join(ordered)
