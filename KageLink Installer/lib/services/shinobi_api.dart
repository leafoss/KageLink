import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/chat_channel.dart';
import '../models/chat_message.dart';
import '../models/runtime_status.dart';

class ShinobiApiException implements Exception {
  const ShinobiApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class ShinobiApi {
  ShinobiApi({required String address, required this.token})
      : baseUri = normalizeAddress(address);

  final Uri baseUri;
  final String token;

  String get displayAddress => baseUri.toString().replaceFirst(RegExp(r'/$'), '');

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
      };

  Uri endpoint(String path, [Map<String, dynamic>? query]) {
    final normalizedPath = path.startsWith('/') ? path : '/$path';
    return baseUri.replace(
      path: normalizedPath,
      queryParameters: query?.map((key, value) => MapEntry(key, value.toString())),
    );
  }

  Uri get websocketUri {
    return baseUri.replace(
      scheme: baseUri.scheme == 'https' ? 'wss' : 'ws',
      path: '/ws',
      queryParameters: {'token': token},
    );
  }

  Future<void> authenticate() async {
    final response = await http
        .post(
          endpoint('/api/auth'),
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode({'token': token}),
        )
        .timeout(const Duration(seconds: 8));
    _ensureSuccess(response, fallback: 'Não foi possível autenticar.');
  }

  Future<RuntimeStatus> fetchStatus() async {
    final response = await http
        .get(endpoint('/api/status'), headers: _headers)
        .timeout(const Duration(seconds: 8));
    final json = _decodeObject(response, fallback: 'Falha ao consultar o servidor.');
    return RuntimeStatus.fromJson(json);
  }

  Future<List<ChatMessage>> fetchHistory({int limit = 800}) async {
    final response = await http
        .get(
          endpoint('/api/history', {'limit': limit}),
          headers: _headers,
        )
        .timeout(const Duration(seconds: 12));
    final json = _decodeObject(response, fallback: 'Falha ao carregar o histórico.');
    final rawMessages = json['messages'];
    if (rawMessages is! List) return const [];
    return rawMessages
        .whereType<Map>()
        .map((item) => ChatMessage.fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false);
  }

  Future<ChatMessage> sendMessage(String message, ChatChannel channel) async {
    final response = await http
        .post(
          endpoint('/api/send'),
          headers: _headers,
          body: jsonEncode({
            'message': message,
            'channel': channel.apiValue,
          }),
        )
        .timeout(const Duration(seconds: 15));
    final json = _decodeObject(response, fallback: 'Falha ao enviar a mensagem.');
    final rawMessage = json['message'];
    if (rawMessage is! Map) {
      throw const ShinobiApiException('O servidor não confirmou a mensagem enviada.');
    }
    return ChatMessage.fromJson(Map<String, dynamic>.from(rawMessage));
  }

  Future<InputCandidateResult> fetchInputCandidates() async {
    final response = await http
        .get(endpoint('/api/input-candidates'), headers: _headers)
        .timeout(const Duration(seconds: 10));
    final json = _decodeObject(response, fallback: 'Falha ao buscar campos de entrada.');
    final rawCandidates = json['candidates'];
    final candidates = rawCandidates is List
        ? rawCandidates
            .whereType<Map>()
            .map((item) => InputCandidate.fromJson(Map<String, dynamic>.from(item)))
            .toList(growable: false)
        : <InputCandidate>[];

    final rawPreferences = json['preferences'];
    final preferences = <ChatChannel, InputControlPreference>{};
    if (rawPreferences is Map) {
      for (final channel in ChatChannel.values) {
        final rawPreference = rawPreferences[channel.apiValue];
        if (rawPreference is Map) {
          preferences[channel] = InputControlPreference.fromJson(
            Map<String, dynamic>.from(rawPreference),
          );
        }
      }
    }

    // Compatibility with agents older than 3.2.0.
    preferences.putIfAbsent(
      ChatChannel.ooc,
      () => InputControlPreference.fromJson({
        'preferred_width': json['preferred_width'],
        'preferred_height': json['preferred_height'],
      }),
    );

    return InputCandidateResult(
      preferences: preferences,
      candidates: candidates,
    );
  }

  Future<void> setInputPreference(
    InputCandidate candidate,
    ChatChannel channel,
  ) async {
    final response = await http
        .post(
          endpoint('/api/input-preference'),
          headers: _headers,
          body: jsonEncode({
            'channel': channel.apiValue,
            'width': candidate.width,
            'height': candidate.height,
            'relative_left': candidate.relativeLeft,
            'relative_top': candidate.relativeTop,
            'candidate_index': candidate.index,
            'parent_class': candidate.parentClass,
          }),
        )
        .timeout(const Duration(seconds: 10));
    _ensureSuccess(response, fallback: 'Falha ao selecionar o campo de entrada.');
  }

  WebSocketChannel connectWebSocket() {
    return WebSocketChannel.connect(websocketUri);
  }

  Map<String, dynamic> _decodeObject(
    http.Response response, {
    required String fallback,
  }) {
    _ensureSuccess(response, fallback: fallback);
    try {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is Map) return Map<String, dynamic>.from(decoded);
    } catch (_) {
      throw ShinobiApiException(fallback, statusCode: response.statusCode);
    }
    throw ShinobiApiException(fallback, statusCode: response.statusCode);
  }

  void _ensureSuccess(http.Response response, {required String fallback}) {
    if (response.statusCode >= 200 && response.statusCode < 300) return;

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

  static Uri normalizeAddress(String rawAddress) {
    var value = rawAddress.trim();
    if (value.isEmpty) {
      throw const FormatException('Informe o IP ou endereço do servidor.');
    }

    value = value.replaceAll(RegExp(r'/+$'), '');
    if (!value.startsWith('http://') && !value.startsWith('https://')) {
      value = 'http://$value';
    }

    final uri = Uri.tryParse(value);
    if (uri == null || uri.host.isEmpty) {
      throw const FormatException('Endereço inválido. Use IP:porta ou uma URL completa.');
    }
    if (uri.scheme != 'http' && uri.scheme != 'https') {
      throw const FormatException('Use http:// ou https:// no endereço.');
    }

    return uri.replace(path: '', query: null, fragment: null);
  }
}
