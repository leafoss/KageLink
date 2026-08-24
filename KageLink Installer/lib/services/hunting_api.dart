import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/hunting_status.dart';
import 'shinobi_api.dart';

extension HuntingApi on ShinobiApi {
  Map<String, String> get _huntingHeaders => {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
      };

  Future<HuntingStatus> fetchHuntingStatus() async {
    final response = await http
        .get(endpoint('/api/hunting/status'), headers: _huntingHeaders)
        .timeout(const Duration(seconds: 8));
    return HuntingStatus.fromJson(
      _huntingObject(response, 'Falha ao consultar o Hunting.'),
    );
  }

  Future<HuntingStatus> startHunting() async {
    final response = await http
        .post(
          endpoint('/api/hunting/start'),
          headers: _huntingHeaders,
          body: jsonEncode({
            'walk_seconds': 1.4,
            'combat_timeout_seconds': 300.0,
            'recovery_timeout_seconds': 600.0,
            'recovery_hp_percent': 90.0,
            'recovery_stamina_percent': 90.0,
          }),
        )
        .timeout(const Duration(seconds: 15));
    return HuntingStatus.fromJson(
      _huntingObject(response, 'Falha ao iniciar o Hunting.'),
    );
  }

  Future<HuntingStatus> stopHunting() async {
    final response = await http
        .post(endpoint('/api/hunting/stop'), headers: _huntingHeaders, body: '{}')
        .timeout(const Duration(seconds: 15));
    return HuntingStatus.fromJson(
      _huntingObject(response, 'Falha ao parar o Hunting.'),
    );
  }

  Map<String, dynamic> _huntingObject(http.Response response, String fallback) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      var message = fallback;
      try {
        final decoded = jsonDecode(utf8.decode(response.bodyBytes));
        if (decoded is Map && decoded['detail'] != null) {
          message = decoded['detail'].toString();
        }
      } catch (_) {}
      throw ShinobiApiException(message, statusCode: response.statusCode);
    }
    try {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is Map) return Map<String, dynamic>.from(decoded);
    } catch (_) {}
    throw ShinobiApiException(fallback, statusCode: response.statusCode);
  }
}
