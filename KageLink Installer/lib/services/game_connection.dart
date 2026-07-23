import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/server_profile.dart';
import 'shinobi_api.dart';

enum GameViewMode { full, zoom }

enum GameStreamState {
  idle,
  connecting,
  live,
  notFound,
  minimized,
  error,
}

class GameConnection extends ChangeNotifier {
  GameConnection(this.profile);

  final ServerProfile profile;

  WebSocketChannel? _streamChannel;
  WebSocketChannel? _controlChannel;
  StreamSubscription<dynamic>? _streamSubscription;
  StreamSubscription<dynamic>? _controlSubscription;
  Timer? _heartbeatTimer;
  Timer? _streamReconnectTimer;
  Timer? _controlReconnectTimer;
  Timer? _fpsTimer;

  Uint8List? _frame;
  GameViewMode _viewMode = GameViewMode.full;
  GameStreamState _streamState = GameStreamState.idle;
  String? _streamMessage;
  bool _active = false;
  bool _controlConnected = false;
  bool _controlActive = false;
  bool _controlsHidden = false;
  int _fps = 0;
  int _framesThisSecond = 0;
  int? _latencyMs;
  Set<String> _movement = <String>{};
  final Set<String> _actions = <String>{};
  Set<String> _lastSentPressed = <String>{};
  bool _focusClickPending = false;

  Uint8List? get frame => _frame;
  GameViewMode get viewMode => _viewMode;
  GameStreamState get streamState => _streamState;
  String? get streamMessage => _streamMessage;
  bool get controlConnected => _controlConnected;
  bool get controlActive => _controlActive;
  bool get controlsHidden => _controlsHidden;
  int get fps => _fps;
  int? get latencyMs => _latencyMs;
  bool get isLive => _streamState == GameStreamState.live && _frame != null;

  Uri _webSocketUri(String path, [Map<String, String>? extraQuery]) {
    final base = ShinobiApi.normalizeAddress(profile.address);
    return base.replace(
      scheme: base.scheme == 'https' ? 'wss' : 'ws',
      path: path,
      queryParameters: <String, String>{
        'token': profile.token,
        ...?extraQuery,
      },
    );
  }

  Future<void> setActive(bool value) async {
    if (_active == value) return;
    _active = value;
    if (value) {
      _focusClickPending = true;
      _startFpsCounter();
      _connectStream();
      _connectControl();
    } else {
      await releaseAndDisconnect();
    }
  }

  void _startFpsCounter() {
    _fpsTimer ??= Timer.periodic(const Duration(seconds: 1), (_) {
      if (!_active) return;
      final next = _framesThisSecond;
      _framesThisSecond = 0;
      if (_fps != next) {
        _fps = next;
        notifyListeners();
      }
    });
  }

  void _connectStream() {
    if (!_active || _streamChannel != null) return;
    _streamReconnectTimer?.cancel();
    _streamState = GameStreamState.connecting;
    _streamMessage = null;
    notifyListeners();

    try {
      final channel = WebSocketChannel.connect(
        _webSocketUri(
          '/ws/game/stream',
          <String, String>{'mode': _viewMode.name},
        ),
      );
      _streamChannel = channel;
      _streamSubscription = channel.stream.listen(
        _handleStreamPayload,
        onError: (Object error) => _handleStreamClosed(error),
        onDone: () => _handleStreamClosed(null),
        cancelOnError: false,
      );
    } catch (error) {
      _handleStreamClosed(error);
    }
  }

  void _handleStreamPayload(dynamic payload) {
    if (!_active) return;
    if (payload is List<int>) {
      _frame = Uint8List.fromList(payload);
      _framesThisSecond += 1;
      _streamState = GameStreamState.live;
      _streamMessage = null;
      notifyListeners();
      return;
    }

    try {
      final decoded = jsonDecode(payload.toString());
      if (decoded is! Map) return;
      final message = Map<String, dynamic>.from(decoded);
      if (message['type']?.toString() != 'stream_status') return;
      switch (message['state']?.toString()) {
        case 'live':
          _streamState = GameStreamState.live;
          _streamMessage = null;
          break;
        case 'not_found':
          _streamState = GameStreamState.notFound;
          _streamMessage = message['message']?.toString();
          _frame = null;
          _releaseLocalControls();
          break;
        case 'minimized':
          _streamState = GameStreamState.minimized;
          _streamMessage = message['message']?.toString();
          _frame = null;
          _releaseLocalControls();
          break;
        default:
          _streamState = GameStreamState.error;
          _streamMessage = message['message']?.toString();
          _frame = null;
          _releaseLocalControls();
          break;
      }
      notifyListeners();
    } catch (_) {
      // Unknown stream packets do not interrupt the game session.
    }
  }

  void _handleStreamClosed(Object? error) {
    _streamSubscription?.cancel();
    _streamSubscription = null;
    _streamChannel = null;
    if (!_active) return;
    _releaseLocalControls();
    if (_streamState != GameStreamState.notFound &&
        _streamState != GameStreamState.minimized) {
      _streamState = GameStreamState.error;
      _streamMessage = error?.toString();
      _frame = null;
      notifyListeners();
    }
    _streamReconnectTimer?.cancel();
    _streamReconnectTimer = Timer(
      const Duration(seconds: 2),
      _connectStream,
    );
  }

  void _connectControl() {
    if (!_active || _controlChannel != null) return;
    _controlReconnectTimer?.cancel();
    try {
      final channel = WebSocketChannel.connect(
        _webSocketUri('/ws/game/control'),
      );
      _controlChannel = channel;
      _controlSubscription = channel.stream.listen(
        _handleControlPayload,
        onError: (Object error) => _handleControlClosed(error),
        onDone: () => _handleControlClosed(null),
        cancelOnError: false,
      );
      _controlConnected = true;
      _sendControl(<String, dynamic>{'type': 'active', 'value': true});
      _heartbeatTimer?.cancel();
      _heartbeatTimer = Timer.periodic(
        const Duration(seconds: 1),
        (_) => _sendHeartbeat(),
      );
      notifyListeners();
    } catch (error) {
      _handleControlClosed(error);
    }
  }

  void _handleControlPayload(dynamic payload) {
    try {
      final decoded = jsonDecode(payload.toString());
      if (decoded is! Map) return;
      final message = Map<String, dynamic>.from(decoded);
      switch (message['type']?.toString()) {
        case 'control_status':
          final state = message['state']?.toString();
          _controlConnected = state != 'heartbeat_timeout';
          _controlActive = state == 'active';
          if (_controlActive && _focusClickPending) {
            _focusClickPending = false;
            _sendControl(<String, dynamic>{'type': 'focus_click'});
          }
          break;
        case 'pong':
          final timestamp = double.tryParse(message['timestamp']?.toString() ?? '');
          if (timestamp != null) {
            _latencyMs = DateTime.now().millisecondsSinceEpoch - timestamp.round();
          }
          _controlConnected = true;
          break;
        case 'control_error':
          _controlActive = false;
          _movement = <String>{};
          _actions.clear();
          _lastSentPressed = <String>{};
          break;
      }
      notifyListeners();
    } catch (_) {
      // Ignore packets from future agent versions.
    }
  }

  void _handleControlClosed(Object? error) {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    _controlSubscription?.cancel();
    _controlSubscription = null;
    _controlChannel = null;
    _controlConnected = false;
    _controlActive = false;
    if (_active) _focusClickPending = true;
    _movement = <String>{};
    _actions.clear();
    _lastSentPressed = <String>{};
    notifyListeners();
    if (!_active) return;
    _controlReconnectTimer?.cancel();
    _controlReconnectTimer = Timer(
      const Duration(seconds: 2),
      _connectControl,
    );
  }

  void _releaseLocalControls() {
    final hadPressed = _movement.isNotEmpty || _actions.isNotEmpty;
    _movement = <String>{};
    _actions.clear();
    if (hadPressed || _lastSentPressed.isNotEmpty) {
      _sendPressedState(force: true);
    }
  }

  void setMovement(Set<String> directions) {
    final safe = directions
        .where((key) => const {'up', 'down', 'left', 'right'}.contains(key))
        .toSet();
    if (setEquals(_movement, safe)) return;
    _movement = safe;
    _sendPressedState();
  }

  void setAction(String key, bool pressed) {
    if (!const {'e', 'space', 'g', 'v'}.contains(key)) return;
    final changed = pressed ? _actions.add(key) : _actions.remove(key);
    if (changed) _sendPressedState();
  }

  void _sendPressedState({bool force = false}) {
    final pressed = <String>{..._movement, ..._actions};
    if (!force && setEquals(pressed, _lastSentPressed)) return;
    _lastSentPressed = Set<String>.from(pressed);
    _sendControl(<String, dynamic>{
      'type': 'keys',
      'pressed': pressed.toList(growable: false),
    });
  }

  void _sendHeartbeat() {
    if (!_active || _controlChannel == null) return;
    if (!_controlActive) {
      _sendControl(<String, dynamic>{'type': 'active', 'value': true});
      return;
    }
    final pressed = <String>{..._movement, ..._actions};
    _sendControl(<String, dynamic>{
      'type': 'heartbeat',
      'pressed': pressed.toList(growable: false),
      'timestamp': DateTime.now().millisecondsSinceEpoch,
    });
  }

  void _sendControl(Map<String, dynamic> payload) {
    try {
      _controlChannel?.sink.add(jsonEncode(payload));
    } catch (_) {
      _handleControlClosed(null);
    }
  }

  Future<void> setViewMode(GameViewMode mode) async {
    if (_viewMode == mode) return;
    _viewMode = mode;
    if (!_active) {
      notifyListeners();
      return;
    }
    await _closeStream();
    _frame = null;
    _connectStream();
    notifyListeners();
  }

  void toggleControls() {
    _controlsHidden = !_controlsHidden;
    if (_controlsHidden) {
      _movement = <String>{};
      _actions.clear();
      _sendPressedState(force: true);
    }
    notifyListeners();
  }

  Future<void> releaseAndDisconnect() async {
    _active = false;
    _focusClickPending = false;
    _streamReconnectTimer?.cancel();
    _controlReconnectTimer?.cancel();
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;

    _movement = <String>{};
    _actions.clear();
    _lastSentPressed = <String>{};
    _sendControl(<String, dynamic>{'type': 'keys', 'pressed': <String>[]});
    _sendControl(<String, dynamic>{'type': 'active', 'value': false});

    await _closeStream();
    await _controlSubscription?.cancel();
    _controlSubscription = null;
    await _controlChannel?.sink.close();
    _controlChannel = null;
    _controlConnected = false;
    _controlActive = false;
    _latencyMs = null;
    _fps = 0;
    _framesThisSecond = 0;
    _streamState = GameStreamState.idle;
    notifyListeners();
  }

  Future<void> _closeStream() async {
    await _streamSubscription?.cancel();
    _streamSubscription = null;
    await _streamChannel?.sink.close();
    _streamChannel = null;
  }

  @override
  void dispose() {
    _active = false;
    _movement = <String>{};
    _actions.clear();
    _sendControl(<String, dynamic>{'type': 'keys', 'pressed': <String>[]});
    _sendControl(<String, dynamic>{'type': 'active', 'value': false});
    _fpsTimer?.cancel();
    _heartbeatTimer?.cancel();
    _streamReconnectTimer?.cancel();
    _controlReconnectTimer?.cancel();
    _streamSubscription?.cancel();
    _controlSubscription?.cancel();
    _streamChannel?.sink.close();
    _controlChannel?.sink.close();
    super.dispose();
  }
}
