class HuntingStatus {
  const HuntingStatus({
    required this.available,
    required this.running,
    required this.phase,
    required this.kills,
    required this.direction,
    required this.lastEnemy,
    required this.health,
    required this.stamina,
    required this.staminaCalibrated,
    required this.lastLine,
    required this.lastError,
  });

  final bool available;
  final bool running;
  final String phase;
  final int kills;
  final String direction;
  final String lastEnemy;
  final double? health;
  final double? stamina;
  final bool staminaCalibrated;
  final String lastLine;
  final String lastError;

  factory HuntingStatus.fromJson(Map<String, dynamic> json) {
    return HuntingStatus(
      available: json['available'] == true,
      running: json['running'] == true,
      phase: json['phase']?.toString() ?? 'idle',
      kills: _integer(json['kills']),
      direction: json['direction']?.toString() ?? '-',
      lastEnemy: json['last_enemy']?.toString() ?? '',
      health: _number(json['health']),
      stamina: _number(json['stamina']),
      staminaCalibrated: json['stamina_calibrated'] == true,
      lastLine: json['last_line']?.toString() ?? '',
      lastError: json['last_error']?.toString() ?? '',
    );
  }

  static int _integer(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }

  static double? _number(dynamic value) {
    if (value == null) return null;
    if (value is num) return value.toDouble();
    return double.tryParse(value.toString());
  }

  String get lastEvent => lastError.trim().isNotEmpty ? lastError : lastLine;
}
