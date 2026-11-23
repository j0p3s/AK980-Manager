# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Interface language for the navigation and page titles (the rest of the interface stays English). Chosen on the System page; applied
the next time the program starts. English is the source text, so a missing translation simply shows the English text."""
LANGUAGES = ('English', 'Português', 'Türkçe')
_PT = {'Overview': 'Resumo', 'Lighting': 'Iluminação', 'Per-key': 'Por tecla', 'Per-key colours': 'Cores por tecla', 'Reactive': 'Reativo',
       'Keys': 'Teclas', 'Key remapping': 'Remapear teclas', 'Macros': 'Macros', 'Screen': 'Ecrã', 'Live screen': 'Ecrã ao vivo',
       'Profiles': 'Perfis', 'Connection': 'Ligação', 'System': 'Sistema', 'HOME': 'INÍCIO', 'LIGHTING': 'ILUMINAÇÃO',
       'KEYS AND MACROS': 'TECLAS E MACROS', 'DEVICE': 'DISPOSITIVO', 'Manager': 'Gestor'}
_TR = {'Overview': 'Genel Bakış', 'Lighting': 'Aydınlatma', 'Per-key': 'Tuş başına', 'Per-key colours': 'Tuş başına renkler',
       'Reactive': 'Reaktif', 'Keys': 'Tuşlar', 'Key remapping': 'Tuş atama', 'Macros': 'Makrolar', 'Screen': 'Ekran',
       'Live screen': 'Canlı ekran', 'Profiles': 'Profiller', 'Connection': 'Bağlantı', 'System': 'Sistem', 'HOME': 'ANA SAYFA',
       'LIGHTING': 'AYDINLATMA', 'KEYS AND MACROS': 'TUŞLAR VE MAKROLAR', 'DEVICE': 'CİHAZ', 'Manager': 'Yönetici'}
TABLES = {'Português': _PT, 'Türkçe': _TR}
current = 'English'


def set_language(name):
    global current
    current = name if name in LANGUAGES else 'English'


def tr(text):
    return TABLES.get(current, {}).get(text, text)
