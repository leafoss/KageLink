class DojoStatus {
  const DojoStatus({
    required this.available,
    required this.running,
    required this.phase,
    required this.currentRound,
    required this.completedRounds,
    required this.lastLine,
    required this.lastError,
    required this.returnCode,
  });

  final bool available;
  final bool running;
  final String phase;
  final int currentRound;
  final int completedRounds;
  final String lastLine;
  final String lastError;
  final int? returnCode;

  factory DojoStatus.fromJson(Map<String, dynamic> json) {
    return DojoStatus(
      available: json['available'] == true,
      running: json['running'] == true,
      phase: json['phase']?.toString() ?? 'idle',
      currentRound: _integer(json['current_round']),
      completedRounds: _integer(json['completed_rounds']),
      lastLine: json['last_line']?.toString() ?? '',
      lastError: json['last_error']?.toString() ?? '',
      returnCode: json['return_code'] == null ? null : _integer(json['return_code']),
    );
  }

  static int _integer(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }

  String get lastEvent => lastError.trim().isNotEmpty ? lastError : lastLine;
}
