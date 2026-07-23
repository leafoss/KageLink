import 'chat_channel.dart';

class RuntimeStatus {
  const RuntimeStatus({
    required this.gameOnline,
    required this.chatFound,
    required this.oocInputFound,
    required this.icInputFound,
    this.chatHwnd,
    this.oocInputHwnd,
    this.icInputHwnd,
    this.lastChatUpdate,
    this.lastSend,
    this.lastError,
  });

  final bool gameOnline;
  final bool chatFound;
  final bool oocInputFound;
  final bool icInputFound;
  final int? chatHwnd;
  final int? oocInputHwnd;
  final int? icInputHwnd;
  final DateTime? lastChatUpdate;
  final DateTime? lastSend;
  final String? lastError;

  bool get inputFound => oocInputFound;
  int? get inputHwnd => oocInputHwnd;
  bool get fullyOperational => gameOnline && chatFound && oocInputFound && icInputFound;

  bool inputFoundFor(ChatChannel channel) {
    return channel == ChatChannel.ic ? icInputFound : oocInputFound;
  }

  factory RuntimeStatus.empty() {
    return const RuntimeStatus(
      gameOnline: false,
      chatFound: false,
      oocInputFound: false,
      icInputFound: false,
    );
  }

  factory RuntimeStatus.fromJson(Map<String, dynamic> json) {
    DateTime? timestamp(dynamic value) {
      final seconds = double.tryParse(value?.toString() ?? '');
      if (seconds == null) return null;
      return DateTime.fromMillisecondsSinceEpoch((seconds * 1000).round()).toLocal();
    }

    final legacyInputFound = json['input_found'] == true;
    return RuntimeStatus(
      gameOnline: json['game_online'] == true,
      chatFound: json['chat_found'] == true,
      oocInputFound: json.containsKey('ooc_input_found')
          ? json['ooc_input_found'] == true
          : legacyInputFound,
      icInputFound: json['ic_input_found'] == true,
      chatHwnd: int.tryParse(json['chat_hwnd']?.toString() ?? ''),
      oocInputHwnd: int.tryParse(
        json['ooc_input_hwnd']?.toString() ?? json['input_hwnd']?.toString() ?? '',
      ),
      icInputHwnd: int.tryParse(json['ic_input_hwnd']?.toString() ?? ''),
      lastChatUpdate: timestamp(json['last_chat_update']),
      lastSend: timestamp(json['last_send']),
      lastError: json['last_error']?.toString(),
    );
  }
}

class InputCandidate {
  const InputCandidate({
    required this.index,
    required this.hwnd,
    required this.left,
    required this.top,
    required this.relativeLeft,
    required this.relativeTop,
    required this.width,
    required this.height,
    required this.visible,
    required this.enabled,
    required this.parentClass,
  });

  final int index;
  final int hwnd;
  final int left;
  final int top;
  final int relativeLeft;
  final int relativeTop;
  final int width;
  final int height;
  final bool visible;
  final bool enabled;
  final String parentClass;

  factory InputCandidate.fromJson(Map<String, dynamic> json) {
    int number(String key) => int.tryParse(json[key]?.toString() ?? '') ?? 0;

    return InputCandidate(
      index: number('index'),
      hwnd: number('hwnd'),
      left: number('left'),
      top: number('top'),
      relativeLeft: number('relative_left'),
      relativeTop: number('relative_top'),
      width: number('width'),
      height: number('height'),
      visible: json['visible'] == true,
      enabled: json['enabled'] == true,
      parentClass: json['parent_class']?.toString() ?? '',
    );
  }
}

class InputControlPreference {
  const InputControlPreference({
    required this.preferredWidth,
    required this.preferredHeight,
    required this.relativeLeft,
    required this.relativeTop,
    required this.candidateIndex,
    required this.parentClass,
  });

  final int preferredWidth;
  final int preferredHeight;
  final int? relativeLeft;
  final int? relativeTop;
  final int? candidateIndex;
  final String parentClass;

  factory InputControlPreference.fromJson(Map<String, dynamic> json) {
    int? optionalNumber(String key) {
      final value = json[key];
      if (value == null) return null;
      return int.tryParse(value.toString());
    }

    return InputControlPreference(
      preferredWidth: optionalNumber('preferred_width') ?? 0,
      preferredHeight: optionalNumber('preferred_height') ?? 0,
      relativeLeft: optionalNumber('relative_left'),
      relativeTop: optionalNumber('relative_top'),
      candidateIndex: optionalNumber('candidate_index'),
      parentClass: json['parent_class']?.toString() ?? '',
    );
  }

  bool matches(InputCandidate candidate) {
    final hasGeometry = preferredWidth > 0 && preferredHeight > 0;
    if (hasGeometry &&
        (candidate.width != preferredWidth || candidate.height != preferredHeight)) {
      return false;
    }
    if (relativeLeft != null && candidate.relativeLeft != relativeLeft) return false;
    if (relativeTop != null && candidate.relativeTop != relativeTop) return false;
    if (candidateIndex != null &&
        !hasGeometry &&
        relativeLeft == null &&
        candidate.index != candidateIndex) {
      return false;
    }
    if (parentClass.isNotEmpty && candidate.parentClass != parentClass) return false;
    return hasGeometry || relativeLeft != null || candidateIndex != null;
  }
}

class InputCandidateResult {
  const InputCandidateResult({
    required this.preferences,
    required this.candidates,
  });

  final Map<ChatChannel, InputControlPreference> preferences;
  final List<InputCandidate> candidates;

  InputControlPreference preferenceFor(ChatChannel channel) {
    return preferences[channel] ??
        const InputControlPreference(
          preferredWidth: 0,
          preferredHeight: 0,
          relativeLeft: null,
          relativeTop: null,
          candidateIndex: null,
          parentClass: '',
        );
  }
}
