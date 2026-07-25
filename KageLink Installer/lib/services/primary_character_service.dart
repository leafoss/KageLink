import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/server_profile.dart';
import 'shinobi_api.dart';

class PrimaryCharacterSetting {
  const PrimaryCharacterSetting({
    required this.primaryCharacter,
    required this.savedCharacters,
  });

  final String primaryCharacter;
  final List<String> savedCharacters;

  factory PrimaryCharacterSetting.fromJson(Map<String, dynamic> json) {
    final rawSaved = json['saved_characters'];
    return PrimaryCharacterSetting(
      primaryCharacter: json['primary_character']?.toString() ?? '',
      savedCharacters: rawSaved is List
          ? rawSaved.map((item) => item.toString()).where((item) => item.isNotEmpty).toList(growable: false)
          : const <String>[],
    );
  }
}

class PrimaryCharacterService {
  const PrimaryCharacterService(this.profile);

  final ServerProfile profile;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ${profile.token}',
      };

  Uri get _endpoint => ShinobiApi.normalizeAddress(profile.address).replace(
        path: '/api/primary-character',
        query: null,
        fragment: null,
      );

  Future<PrimaryCharacterSetting> fetch() async {
    final response = await http
        .get(_endpoint, headers: _headers)
        .timeout(const Duration(seconds: 8));
    return _decode(response, 'Não foi possível carregar o personagem principal.');
  }

  Future<PrimaryCharacterSetting> save(String name) async {
    final response = await http
        .post(
          _endpoint,
          headers: _headers,
          body: jsonEncode({'name': name.trim()}),
        )
        .timeout(const Duration(seconds: 8));
    return _decode(response, 'Não foi possível salvar o personagem principal.');
  }

  PrimaryCharacterSetting _decode(http.Response response, String fallback) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      String message = fallback;
      try {
        final decoded = jsonDecode(utf8.decode(response.bodyBytes));
        if (decoded is Map && decoded['detail'] != null) {
          message = decoded['detail'].toString();
        }
      } catch (_) {}
      if (response.statusCode == 401) message = 'Token inválido.';
      throw ShinobiApiException(message, statusCode: response.statusCode);
    }

    try {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is Map) {
        return PrimaryCharacterSetting.fromJson(Map<String, dynamic>.from(decoded));
      }
    } catch (_) {}
    throw ShinobiApiException(fallback, statusCode: response.statusCode);
  }
}
