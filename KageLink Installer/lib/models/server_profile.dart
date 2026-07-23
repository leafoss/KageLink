enum ConnectionKind {
  internal,
  external,
  custom;

  String get label => switch (this) {
        ConnectionKind.internal => 'Rede interna',
        ConnectionKind.external => 'IP externo',
        ConnectionKind.custom => 'Personalizado',
      };

  String get shortLabel => switch (this) {
        ConnectionKind.internal => 'Interno',
        ConnectionKind.external => 'Externo',
        ConnectionKind.custom => 'Outro',
      };

  static ConnectionKind fromName(String? value) {
    return ConnectionKind.values.firstWhere(
      (item) => item.name == value,
      orElse: () => ConnectionKind.custom,
    );
  }
}

class ServerProfile {
  const ServerProfile({
    required this.id,
    required this.name,
    required this.address,
    required this.token,
    required this.kind,
    required this.favorite,
    required this.lastUsedAt,
  });

  final String id;
  final String name;
  final String address;
  final String token;
  final ConnectionKind kind;
  final bool favorite;
  final DateTime lastUsedAt;

  ServerProfile copyWith({
    String? id,
    String? name,
    String? address,
    String? token,
    ConnectionKind? kind,
    bool? favorite,
    DateTime? lastUsedAt,
  }) {
    return ServerProfile(
      id: id ?? this.id,
      name: name ?? this.name,
      address: address ?? this.address,
      token: token ?? this.token,
      kind: kind ?? this.kind,
      favorite: favorite ?? this.favorite,
      lastUsedAt: lastUsedAt ?? this.lastUsedAt,
    );
  }

  Map<String, dynamic> toPersistedJson() {
    return {
      'id': id,
      'name': name,
      'address': address,
      'kind': kind.name,
      'favorite': favorite,
      'lastUsedAt': lastUsedAt.toUtc().toIso8601String(),
    };
  }

  factory ServerProfile.fromPersistedJson(
    Map<String, dynamic> json, {
    required String token,
  }) {
    return ServerProfile(
      id: json['id']?.toString() ?? '',
      name: json['name']?.toString() ?? 'Servidor',
      address: json['address']?.toString() ?? '',
      token: token,
      kind: ConnectionKind.fromName(json['kind']?.toString()),
      favorite: json['favorite'] == true,
      lastUsedAt: DateTime.tryParse(json['lastUsedAt']?.toString() ?? '') ??
          DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
    );
  }

  static String createId() {
    return DateTime.now().microsecondsSinceEpoch.toString();
  }
}
