import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class LocaleController extends ChangeNotifier {
  LocaleController() : _preferences = SharedPreferencesAsync();

  static const _localeKey = 'kagelink.locale.v1';

  final SharedPreferencesAsync _preferences;
  Locale _locale = const Locale('pt', 'BR');

  Locale get locale => _locale;

  Future<void> initialize() async {
    final saved = await _preferences.getString(_localeKey);
    if (saved != null) {
      _locale = _parse(saved);
      return;
    }

    final systemLocale = PlatformDispatcher.instance.locale;
    _locale = systemLocale.languageCode.toLowerCase() == 'en'
        ? const Locale('en', 'US')
        : const Locale('pt', 'BR');
  }

  Future<void> setLocale(Locale locale) async {
    final normalized = locale.languageCode.toLowerCase() == 'en'
        ? const Locale('en', 'US')
        : const Locale('pt', 'BR');
    if (_locale == normalized) return;
    _locale = normalized;
    await _preferences.setString(_localeKey, normalized.toLanguageTag());
    notifyListeners();
  }

  Locale _parse(String raw) {
    return raw.toLowerCase().startsWith('en')
        ? const Locale('en', 'US')
        : const Locale('pt', 'BR');
  }
}
