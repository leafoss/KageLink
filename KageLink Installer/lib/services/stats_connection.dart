import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/server_profile.dart';
import 'shinobi_api.dart';

enum StatsStreamState {
  idle,
  connecting,
  live,
  notFound,
  minimized,
  error,
}

class StatsConnection extends ChangeNotifier {
  StatsConnection(this.profile);

  final ServerProfile profile;

  WebSocketChannel? _streamChannel;
  WebSocketChannel? _controlChannel;
  StreamSubscription<dynamic>? _streamSubscription;
  StreamSubscription<dynamic>? _controlSubscription;
  Timer? _streamReconnectTimer;
  Timer? _controlReconnectTimer;
  Timer? _heartbeatTimer;
  Timer? _fpsTimer;

  Uint8List? _frame;
  StatsStreamState _streamState = StatsStreamState.idle;
  String? _message;
  bool _active = false;
  bool _controlConnected = false;
  bool _controlActive = false;
  bool _openPending = false;
  int _frameWidth = 0;
  int _frameHeight = 0;
  int? _windowId;
  int _fps = 0;
  int _framesThisSecond = 0;
  int? _latencyMs;

  Uint8List? get frame => _frame;
  StatsStreamState get streamState => _streamState;
  String? get message => _message;
  bool get controlConnected => _controlConnected;
  bool get controlActive => _controlActive;
  int get frameWidth => _frameWidth;
  int get frameHeight => _frameHeight;
  int get fps => _fps;
  int? get latencyMs => _latencyMs;
  bool get isLive => _streamState == StatsStreamState.live && _frame != null;

  Uri _webSocketUri(String path) {
    final base = ShinobiApi.normalizeAddress(profile.address);
    return base.replace(
      scheme: base.scheme == 'https' ? 'wss' : 'ws',
      path: path,
      queryParameters: <String, String>{'token': profile.token},
    );
  }

  Future<void> setActive(bool value) async {
    if (_active == value) {
      if (value) requestOpen();
      return;
    }
    _active = value;
    if (value) {
      _openPending = true;
      _startFpsCounter();
      _connectControl();
      _connectStream();
    } else {
      await disconnect();
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
    _streamState = StatsStreamState.connecting;
    _message = null;
    notifyListeners();
    try {
      final channel = WebSocketChannel.connect(
        _webSocketUri('/ws/stats/stream'),
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
      _streamState = StatsStreamState.live;
      _message = null;
      notifyListeners();
      return;
    }

    try {
      final decoded = jsonDecode(payload.toString());
      if (decoded is! Map) return;
      final packet = Map<String, dynamic>.from(decoded);
      if (packet['type']?.toString() != 'stats_stream_status') return;
      final width = int.tryParse(packet['output_width']?.toString() ?? '');
      final windowId = int.tryParse(packet['window_hwnd']?.toString() ?? '');
      final height = int.tryParse(packet['output_height']?.toString() ?? '');
      final geometryChanged =
          (width != null && width > 0 && width != _frameWidth) ||
          (height != null && height > 0 && height != _frameHeight) ||
          (windowId != null && windowId > 0 && windowId != _windowId);
      if (geometryChanged) _frame = null;
      if (width != null && width > 0) _frameWidth = width;
      if (height != null && height > 0) _frameHeight = height;
      if (windowId != null && windowId > 0) _windowId = windowId;
      switch (packet['state']?.toString()) {
        case 'live':
          _streamState = StatsStreamState.live;
          _message = null;
          break;
        case 'not_found':
          _streamState = StatsStreamState.notFound;
          _message = packet['message']?.toString();
          _frame = null;
          _windowId = null;
          break;
        case 'minimized':
          _streamState = StatsStreamState.minimized;
          _message = packet['message']?.toString();
          _frame = null;
          _windowId = null;
          break;
        default:
          _streamState = StatsStreamState.error;
          _message = packet['message']?.toString();
          _frame = null;
          _windowId = null;
          break;
      }
      notifyListeners();
    } catch (_) {
      // Ignore future protocol packets without interrupting the session.
    }
  }

  void _handleStreamClosed(Object? error) {
    _streamSubscription?.cancel();
    _streamSubscription = null;
    _streamChannel = null;
    if (!_active) return;
    if (_streamState != StatsStreamState.notFound &&
        _streamState != StatsStreamState.minimized) {
      _streamState = StatsStreamState.error;
      _message = error?.toString();
      _frame = null;
      _windowId = null;
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
        _webSocketUri('/ws/stats/control'),
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
        const Duration(seconds: 2),
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
      final packet = Map<String, dynamic>.from(decoded);
      switch (packet['type']?.toString()) {
        case 'stats_control_status':
          final state = packet['state']?.toString();
          _controlConnected = state != 'heartbeat_timeout';
          _controlActive = state == 'active';
          if (_controlActive && _openPending) {
            _openPending = false;
            _sendControl(<String, dynamic>{'type': 'open_stats'});
          }
          break;
        case 'stats_open_status':
          final state = packet['state']?.toString();
          if (state == 'error') {
            _message = packet['message']?.toString();
          } else {
            _message = null;
          }
          break;
        case 'stats_click_status':
          if (packet['state']?.toString() == 'error') {
            _message = packet['message']?.toString();
          }
          break;
        case 'pong':
          final timestamp =
              double.tryParse(packet['timestamp']?.toString() ?? '');
          if (timestamp != null) {
            _latencyMs =
                DateTime.now().millisecondsSinceEpoch - timestamp.round();
          }
          _controlConnected = true;
          break;
        case 'stats_control_error':
          _controlActive = false;
          _message = packet['message']?.toString();
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
    if (_active) _openPending = true;
    if (error != null) _message = error.toString();
    notifyListeners();
    if (!_active) return;
    _controlReconnectTimer?.cancel();
    _controlReconnectTimer = Timer(
      const Duration(seconds: 2),
      _connectControl,
    );
  }

  void requestOpen() {
    if (!_active) return;
    _openPending = true;
    if (_controlActive) {
      _openPending = false;
      _sendControl(<String, dynamic>{'type': 'open_stats'});
    } else {
      _connectControl();
    }
    if (_streamChannel == null) _connectStream();
  }

  void sendClick({
    required double x,
    required double y,
    required String button,
  }) {
    if (!_active || !_controlActive || _windowId == null) return;
    if (x < 0 || x > 1 || y < 0 || y > 1) return;
    if (button != 'left' && button != 'right') return;
    _sendControl(<String, dynamic>{
      'type': 'click',
      'x': x,
      'y': y,
      'button': button,
      'window_id': _windowId,
    });
  }

  void _sendHeartbeat() {
    if (!_active || _controlChannel == null) return;
    if (!_controlActive) {
      _sendControl(<String, dynamic>{'type': 'active', 'value': true});
      return;
    }
    _sendControl(<String, dynamic>{
      'type': 'heartbeat',
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

  Future<void> disconnect() async {
    _active = false;
    _openPending = false;
    _streamReconnectTimer?.cancel();
    _controlReconnectTimer?.cancel();
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    _sendControl(<String, dynamic>{'type': 'active', 'value': false});
    await _streamSubscription?.cancel();
    _streamSubscription = null;
    await _streamChannel?.sink.close();
    _streamChannel = null;
    await _controlSubscription?.cancel();
    _controlSubscription = null;
    await _controlChannel?.sink.close();
    _controlChannel = null;
    _controlConnected = false;
    _controlActive = false;
    _latencyMs = null;
    _fps = 0;
    _framesThisSecond = 0;
    _streamState = StatsStreamState.idle;
    _message = null;
    _frame = null;
    _frameWidth = 0;
    _frameHeight = 0;
    _windowId = null;
    notifyListeners();
  }

  @override
  void dispose() {
    _active = false;
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
