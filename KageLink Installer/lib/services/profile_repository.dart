import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/server_profile.dart';

class ProfileRepository {
  ProfileRepository()
      : _preferences = SharedPreferencesAsync(),
        _secureStorage = const FlutterSecureStorage();

  static const _profilesKey = 'kagelink.server_profiles.v1';
  static const _lastProfileKey = 'kagelink.last_profile.v1';
  static const _tokenPrefix = 'kagelink.token.';

  final SharedPreferencesAsync _preferences;
  final FlutterSecureStorage _secureStorage;

  Future<List<ServerProfile>> loadProfiles() async {
    final raw = await _preferences.getString(_profilesKey);
    if (raw == null || raw.trim().isEmpty) return <ServerProfile>[];

    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) return <ServerProfile>[];

      final profiles = <ServerProfile>[];
      for (final item in decoded) {
        if (item is! Map) continue;
        final json = Map<String, dynamic>.from(item);
        final id = json['id']?.toString() ?? '';
        if (id.isEmpty) continue;
        final token = await _secureStorage.read(key: '$_tokenPrefix$id') ?? '';
        profiles.add(ServerProfile.fromPersistedJson(json, token: token));
      }

      profiles.sort(_sortProfiles);
      return profiles;
    } catch (_) {
      return <ServerProfile>[];
    }
  }

  Future<ServerProfile> saveProfile(ServerProfile profile) async {
    final profiles = List<ServerProfile>.of(await loadProfiles());
    final normalized = profile.copyWith(
      name: profile.name.trim().isEmpty ? 'Servidor Shinobi' : profile.name.trim(),
      address: profile.address.trim(),
      lastUsedAt: DateTime.now(),
    );

    final index = profiles.indexWhere((item) => item.id == normalized.id);
    if (index >= 0) {
      profiles[index] = normalized;
    } else {
      profiles.add(normalized);
    }

    profiles.sort(_sortProfiles);
    await _writeProfiles(profiles);
    await _secureStorage.write(
      key: '$_tokenPrefix${normalized.id}',
      value: normalized.token,
    );
    await _preferences.setString(_lastProfileKey, normalized.id);
    return normalized;
  }

  Future<void> deleteProfile(String id) async {
    final profiles = List<ServerProfile>.of(await loadProfiles());
    profiles.removeWhere((item) => item.id == id);
    await _writeProfiles(profiles);
    await _secureStorage.delete(key: '$_tokenPrefix$id');

    final lastId = await _preferences.getString(_lastProfileKey);
    if (lastId == id) await _preferences.remove(_lastProfileKey);
  }

  Future<void> toggleFavorite(String id) async {
    final profiles = List<ServerProfile>.of(await loadProfiles());
    final index = profiles.indexWhere((item) => item.id == id);
    if (index < 0) return;
    profiles[index] = profiles[index].copyWith(favorite: !profiles[index].favorite);
    profiles.sort(_sortProfiles);
    await _writeProfiles(profiles);
  }

  Future<String?> loadLastProfileId() {
    return _preferences.getString(_lastProfileKey);
  }

  Future<void> _writeProfiles(List<ServerProfile> profiles) async {
    final encoded = jsonEncode(
      profiles.map((item) => item.toPersistedJson()).toList(growable: false),
    );
    await _preferences.setString(_profilesKey, encoded);
  }

  int _sortProfiles(ServerProfile a, ServerProfile b) {
    if (a.favorite != b.favorite) return a.favorite ? -1 : 1;
    return b.lastUsedAt.compareTo(a.lastUsedAt);
  }
}
