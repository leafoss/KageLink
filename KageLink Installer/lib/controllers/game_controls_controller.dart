import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum GameButtonBank { abcd, zxvu }

class GameKeyOption {
  const GameKeyOption(this.id, this.label);

  final String id;
  final String label;
}

class GameControlsController extends ChangeNotifier {
  GameControlsController() {
    unawaited(_load());
  }

  static const Map<String, String> defaultAbcd = <String, String>{
    'A': 'e',
    'B': 'space',
    'C': 'g',
    'D': 'v',
  };

  static const Map<String, String> defaultZxvu = <String, String>{
    'Z': 'z',
    'X': 'x',
    'V': 'v',
    'U': 'u',
  };

  static const List<GameKeyOption> supportedKeys = <GameKeyOption>[
    GameKeyOption('a', 'A'),
    GameKeyOption('b', 'B'),
    GameKeyOption('c', 'C'),
    GameKeyOption('d', 'D'),
    GameKeyOption('e', 'E'),
    GameKeyOption('f', 'F'),
    GameKeyOption('g', 'G'),
    GameKeyOption('h', 'H'),
    GameKeyOption('i', 'I'),
    GameKeyOption('j', 'J'),
    GameKeyOption('k', 'K'),
    GameKeyOption('l', 'L'),
    GameKeyOption('m', 'M'),
    GameKeyOption('n', 'N'),
    GameKeyOption('o', 'O'),
    GameKeyOption('p', 'P'),
    GameKeyOption('q', 'Q'),
    GameKeyOption('r', 'R'),
    GameKeyOption('s', 'S'),
    GameKeyOption('t', 'T'),
    GameKeyOption('u', 'U'),
    GameKeyOption('v', 'V'),
    GameKeyOption('w', 'W'),
    GameKeyOption('x', 'X'),
    GameKeyOption('y', 'Y'),
    GameKeyOption('z', 'Z'),
    GameKeyOption('0', '0'),
    GameKeyOption('1', '1'),
    GameKeyOption('2', '2'),
    GameKeyOption('3', '3'),
    GameKeyOption('4', '4'),
    GameKeyOption('5', '5'),
    GameKeyOption('6', '6'),
    GameKeyOption('7', '7'),
    GameKeyOption('8', '8'),
    GameKeyOption('9', '9'),
    GameKeyOption('up', 'UP'),
    GameKeyOption('down', 'DOWN'),
    GameKeyOption('left', 'LEFT'),
    GameKeyOption('right', 'RIGHT'),
    GameKeyOption('space', 'SPACE'),
    GameKeyOption('enter', 'ENTER'),
    GameKeyOption('escape', 'ESC'),
    GameKeyOption('tab', 'TAB'),
    GameKeyOption('shift', 'SHIFT'),
    GameKeyOption('ctrl', 'CTRL'),
    GameKeyOption('alt', 'ALT'),
    GameKeyOption('backspace', 'BACKSPACE'),
    GameKeyOption('insert', 'INSERT'),
    GameKeyOption('delete', 'DELETE'),
    GameKeyOption('home', 'HOME'),
    GameKeyOption('end', 'END'),
    GameKeyOption('pageup', 'PAGE UP'),
    GameKeyOption('pagedown', 'PAGE DOWN'),
    GameKeyOption('f1', 'F1'),
    GameKeyOption('f2', 'F2'),
    GameKeyOption('f3', 'F3'),
    GameKeyOption('f4', 'F4'),
    GameKeyOption('f5', 'F5'),
    GameKeyOption('f6', 'F6'),
    GameKeyOption('f7', 'F7'),
    GameKeyOption('f8', 'F8'),
    GameKeyOption('f9', 'F9'),
    GameKeyOption('f10', 'F10'),
    GameKeyOption('f11', 'F11'),
    GameKeyOption('f12', 'F12'),
  ];

  static final Set<String> supportedKeyIds =
      supportedKeys.map((option) => option.id).toSet();

  static const String _mappingPrefix = 'game_control_mapping_';
  static const String _bankPreference = 'game_control_active_bank';

  final Map<String, String> _mappings = <String, String>{
    ...defaultAbcd,
    ...defaultZxvu,
  };

  GameButtonBank _activeBank = GameButtonBank.abcd;
  bool _loaded = false;
  bool _disposed = false;

  bool get loaded => _loaded;
  GameButtonBank get activeBank => _activeBank;

  List<String> get activeButtons => _activeBank == GameButtonBank.abcd
      ? const <String>['A', 'B', 'C', 'D']
      : const <String>['Z', 'X', 'V', 'U'];

  String mappingFor(String button) {
    return _mappings[button] ??
        defaultAbcd[button] ??
        defaultZxvu[button] ??
        'e';
  }

  String displayLabelForKey(String key) {
    for (final option in supportedKeys) {
      if (option.id == key) return option.label;
    }
    return key.toUpperCase();
  }

  Future<void> _load() async {
    final preferences = await SharedPreferences.getInstance();
    for (final entry in <String, String>{
      ...defaultAbcd,
      ...defaultZxvu,
    }.entries) {
      final stored = preferences.getString('$_mappingPrefix${entry.key}');
      _mappings[entry.key] =
          stored != null && supportedKeyIds.contains(stored)
              ? stored
              : entry.value;
    }
    final storedBank = preferences.getString(_bankPreference);
    _activeBank = storedBank == GameButtonBank.zxvu.name
        ? GameButtonBank.zxvu
        : GameButtonBank.abcd;
    _loaded = true;
    if (!_disposed) notifyListeners();
  }

  Future<void> setMapping(String button, String key) async {
    if (!_mappings.containsKey(button) || !supportedKeyIds.contains(key)) {
      throw ArgumentError('Unsupported game control mapping: $button -> $key');
    }
    if (_mappings[button] == key) return;
    _mappings[button] = key;
    notifyListeners();
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString('$_mappingPrefix$button', key);
  }

  Future<void> setActiveBank(GameButtonBank bank) async {
    if (_activeBank == bank) return;
    _activeBank = bank;
    notifyListeners();
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(_bankPreference, bank.name);
  }

  Future<void> toggleBank() {
    return setActiveBank(
      _activeBank == GameButtonBank.abcd
          ? GameButtonBank.zxvu
          : GameButtonBank.abcd,
    );
  }

  Future<void> resetBank(GameButtonBank bank) async {
    final defaults = bank == GameButtonBank.abcd ? defaultAbcd : defaultZxvu;
    _mappings.addAll(defaults);
    notifyListeners();
    final preferences = await SharedPreferences.getInstance();
    await Future.wait(
      defaults.entries.map(
        (entry) => preferences.setString(
          '$_mappingPrefix${entry.key}',
          entry.value,
        ),
      ),
    );
  }

  Future<void> resetAll() async {
    _mappings
      ..addAll(defaultAbcd)
      ..addAll(defaultZxvu);
    _activeBank = GameButtonBank.abcd;
    notifyListeners();
    final preferences = await SharedPreferences.getInstance();
    await Future.wait(<Future<bool>>[
      for (final entry in <String, String>{
        ...defaultAbcd,
        ...defaultZxvu,
      }.entries)
        preferences.setString('$_mappingPrefix${entry.key}', entry.value),
      preferences.setString(_bankPreference, GameButtonBank.abcd.name),
    ]);
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
