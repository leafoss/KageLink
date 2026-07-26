import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/chat_channel.dart';
import '../models/chat_message.dart';
import '../models/runtime_status.dart';
import '../models/server_profile.dart';
import '../services/profile_repository.dart';
import '../services/shinobi_api.dart';

enum ConnectionPhase {
  idle,
  connecting,
  connected,
  reconnecting,
  failed,
}

class SessionController extends ChangeNotifier {
  SessionController(this._repository);

  final ProfileRepository _repository;
  final Map<int, ChatMessage> _messagesById = {};

  List<ServerProfile> _profiles = const [];
  ServerProfile? _activeProfile;
  ShinobiApi? _api;
  RuntimeStatus _status = RuntimeStatus.empty();
  ConnectionPhase _phase = ConnectionPhase.idle;
  String? _errorMessage;
  bool _sending = false;
  bool _loadingProfiles = true;
  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _socketSubscription;
  Timer? _pingTimer;
  Timer? _reconnectTimer;
  Timer? _historySyncTimer;
  bool _historySyncInFlight = false;
  int _reconnectAttempt = 0;

  List<ServerProfile> get profiles => List.unmodifiable(_profiles);
  List<ChatMessage> get messages {
    final list = _messagesById.values.toList(growable: false);
    list.sort((a, b) => a.id.compareTo(b.id));
    return list;
  }

  ServerProfile? get activeProfile => _activeProfile;
  RuntimeStatus get status => _status;
  ConnectionPhase get phase => _phase;
  String? get errorMessage => _errorMessage;
  bool get sending => _sending;
  bool get loadingProfiles => _loadingProfiles;
  bool get isConnected => _phase == ConnectionPhase.connected;

  Future<void> initialize() async {
    _loadingProfiles = true;
    notifyListeners();
    _profiles = await _repository.loadProfiles();
    _loadingProfiles = false;
    notifyListeners();
  }

  Future<void> connect(ServerProfile draft) async {
    await _closeSocket();
    _phase = ConnectionPhase.connecting;
    _errorMessage = null;
    notifyListeners();

    try {
      final candidateApi = ShinobiApi(address: draft.address, token: draft.token);
      await candidateApi.authenticate();

      final results = await Future.wait<dynamic>([
        candidateApi.fetchHistory(limit: 1000),
        candidateApi.fetchStatus(),
      ]);

      final saved = await _repository.saveProfile(
        draft.copyWith(address: candidateApi.displayAddress),
      );

      _api = candidateApi;
      _activeProfile = saved;
      _messagesById.clear();
      _mergeMessages(results[0] as List<ChatMessage>);
      _status = results[1] as RuntimeStatus;
      _profiles = await _repository.loadProfiles();
      _phase = ConnectionPhase.connected;
      _reconnectAttempt = 0;
      notifyListeners();
      _startHistorySync();
      _connectWebSocket();
    } catch (error) {
      _phase = ConnectionPhase.failed;
      _errorMessage = _friendlyError(error);
      notifyListeners();
      rethrow;
    }
  }

  Future<void> switchServer() async {
    await _closeSocket();
    _api = null;
    _activeProfile = null;
    _messagesById.clear();
    _status = RuntimeStatus.empty();
    _phase = ConnectionPhase.idle;
    _errorMessage = null;
    notifyListeners();
  }

  Future<void> refresh() async {
    final api = _requireApi();
    try {
      final results = await Future.wait<dynamic>([
        api.fetchHistory(limit: 1000),
        api.fetchStatus(),
      ]);
      _mergeMessages(results[0] as List<ChatMessage>);
      _status = results[1] as RuntimeStatus;
      _errorMessage = null;
      notifyListeners();
    } catch (error) {
      _errorMessage = _friendlyError(error);
      notifyListeners();
      rethrow;
    }
  }

  Future<void> sendOocMessage(String rawMessage) {
    return _sendChannelMessage(rawMessage, ChatChannel.ooc);
  }

  Future<void> sendIcMessage(String rawMessage) {
    return _sendChannelMessage(rawMessage, ChatChannel.ic);
  }

  Future<void> sendMessage(String rawMessage, ChatChannel channel) {
    return channel == ChatChannel.ic
        ? sendIcMessage(rawMessage)
        : sendOocMessage(rawMessage);
  }

  Future<void> _sendChannelMessage(
    String rawMessage,
    ChatChannel channel,
  ) async {
    final message = rawMessage.trim();
    if (message.isEmpty || _sending) return;

    _sending = true;
    _errorMessage = null;
    notifyListeners();
    try {
      final api = _requireApi();
      final sent = channel == ChatChannel.ic
          ? await api.sendIcMessage(message)
          : await api.sendOocMessage(message);
      if (sent.channel != channel) {
        throw const ShinobiApiException('O servidor confirmou o canal incorreto.');
      }
      _messagesById[sent.id] = sent;
      notifyListeners();
    } catch (error) {
      _errorMessage = _friendlyError(error);
      notifyListeners();
      rethrow;
    } finally {
      _sending = false;
      notifyListeners();
    }
  }

  Future<InputCandidateResult> fetchInputCandidates() {
    return _requireApi().fetchInputCandidates();
  }

  Future<void> selectInputCandidate(
    InputCandidate candidate,
    ChatChannel channel,
  ) async {
    await _requireApi().setInputPreference(candidate, channel);
    await refresh();
  }

  Future<void> toggleFavorite(String id) async {
    await _repository.toggleFavorite(id);
    _profiles = await _repository.loadProfiles();
    notifyListeners();
  }

  Future<void> deleteProfile(String id) async {
    if (_activeProfile?.id == id) await switchServer();
    await _repository.deleteProfile(id);
    _profiles = await _repository.loadProfiles();
    notifyListeners();
  }

  void clearError() {
    _errorMessage = null;
    notifyListeners();
  }

  bool _mergeMessages(Iterable<ChatMessage> messages) {
    var changed = false;
    for (final message in messages) {
      final previous = _messagesById[message.id];
      if (previous == null ||
          previous.timestamp != message.timestamp ||
          previous.direction != message.direction ||
          previous.channel != message.channel ||
          previous.text != message.text ||
          previous.resynchronized != message.resynchronized) {
        _messagesById[message.id] = message;
        changed = true;
      }
    }
    return changed;
  }

  void _startHistorySync() {
    _historySyncTimer?.cancel();
    _historySyncTimer = Timer.periodic(const Duration(seconds: 2), (_) {
      unawaited(_syncHistoryFallback());
    });
    unawaited(_syncHistoryFallback());
  }

  Future<void> _syncHistoryFallback() async {
    final api = _api;
    if (api == null || _activeProfile == null || _historySyncInFlight) return;

    _historySyncInFlight = true;
    try {
      // WebSocket remains the low-latency path. This HTTP reconciliation is a
      // deliberate second path so OOC/IC history cannot silently freeze when a
      // tunnel/proxy keeps normal HTTP working but drops the chat WebSocket.
      final history = await api.fetchHistory(limit: 1000);
      if (_mergeMessages(history)) {
        notifyListeners();
      }
    } catch (error) {
      // Do not tear down an otherwise usable connection. The socket reconnect
      // loop and the next reconciliation tick will retry independently.
      debugPrint('KageLink history sync fallback: $error');
    } finally {
      _historySyncInFlight = false;
    }
  }

  void _connectWebSocket() {
    final api = _api;
    if (api == null || _activeProfile == null) return;

    _socketSubscription?.cancel();
    _channel?.sink.close();
    _pingTimer?.cancel();
    _reconnectTimer?.cancel();

    try {
      final channel = api.connectWebSocket();
      _channel = channel;
      _socketSubscription = channel.stream.listen(
        _handleSocketPayload,
        onError: (Object error) => _scheduleReconnect(error),
        onDone: () => _scheduleReconnect(null),
        cancelOnError: false,
      );
      _phase = ConnectionPhase.connected;
      _errorMessage = null;
      _reconnectAttempt = 0;
      _pingTimer = Timer.periodic(const Duration(seconds: 20), (_) {
        try {
          _channel?.sink.add('ping');
        } catch (_) {}
      });
      notifyListeners();
    } catch (error) {
      _scheduleReconnect(error);
    }
  }

  void _handleSocketPayload(dynamic rawPayload) {
    try {
      final decoded = jsonDecode(rawPayload.toString());
      if (decoded is! Map) return;
      final payload = Map<String, dynamic>.from(decoded);
      switch (payload['type']?.toString()) {
        case 'message':
          final rawMessage = payload['message'];
          if (rawMessage is Map) {
            final message = ChatMessage.fromJson(Map<String, dynamic>.from(rawMessage));
            _messagesById[message.id] = message;
            notifyListeners();
          }
          break;
        case 'status':
          final rawStatus = payload['status'];
          if (rawStatus is Map) {
            _status = RuntimeStatus.fromJson(Map<String, dynamic>.from(rawStatus));
            notifyListeners();
          }
          break;
        case 'error':
          _errorMessage = payload['message']?.toString() ?? 'Erro informado pelo servidor.';
          notifyListeners();
          break;
        default:
          break;
      }
    } catch (_) {
      // Pacotes desconhecidos são ignorados para manter a sessão viva.
    }
  }

  void _scheduleReconnect(Object? error) {
    _pingTimer?.cancel();
    _socketSubscription?.cancel();
    _channel = null;
    if (_activeProfile == null || _api == null) return;
    if (_reconnectTimer?.isActive == true) return;

    _phase = ConnectionPhase.reconnecting;
    if (error != null) _errorMessage = _friendlyError(error);
    notifyListeners();

    _reconnectAttempt += 1;
    final index = _reconnectAttempt > 4 ? 4 : _reconnectAttempt;
    final seconds = <int>[2, 4, 8, 16, 16][index];
    _reconnectTimer = Timer(Duration(seconds: seconds), () async {
      if (_activeProfile == null || _api == null) return;
      try {
        final results = await Future.wait<dynamic>([
          _api!.fetchHistory(limit: 1000),
          _api!.fetchStatus(),
        ]);
        _mergeMessages(results[0] as List<ChatMessage>);
        _status = results[1] as RuntimeStatus;
        notifyListeners();
        _connectWebSocket();
      } catch (reconnectError) {
        _scheduleReconnect(reconnectError);
      }
    });
  }

  Future<void> _closeSocket() async {
    _historySyncTimer?.cancel();
    _historySyncTimer = null;
    _historySyncInFlight = false;
    _reconnectTimer?.cancel();
    _pingTimer?.cancel();
    await _socketSubscription?.cancel();
    await _channel?.sink.close();
    _channel = null;
    _socketSubscription = null;
  }

  ShinobiApi _requireApi() {
    final api = _api;
    if (api == null) throw const ShinobiApiException('Nenhum servidor está conectado.');
    return api;
  }

  String _friendlyError(Object error) {
    if (error is ShinobiApiException) return error.message;
    if (error is FormatException) return error.message;
    if (error is TimeoutException) return 'O servidor demorou demais para responder.';
    final text = error.toString();
    if (text.contains('SocketException') || text.contains('Connection refused')) {
      return 'Não foi possível alcançar esse IP e porta.';
    }
    return text.replaceFirst('Exception: ', '');
  }

  @override
  void dispose() {
    _historySyncTimer?.cancel();
    _reconnectTimer?.cancel();
    _pingTimer?.cancel();
    _socketSubscription?.cancel();
    _channel?.sink.close();
    super.dispose();
  }
}
