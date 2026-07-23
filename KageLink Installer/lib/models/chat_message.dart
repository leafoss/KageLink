import 'chat_channel.dart';

class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.timestamp,
    required this.direction,
    required this.channel,
    required this.text,
    required this.resynchronized,
  });

  final int id;
  final DateTime timestamp;
  final String direction;
  final ChatChannel channel;
  final String text;
  final bool resynchronized;

  bool get isOutgoing => direction == 'outgoing';
  bool get isIc => channel == ChatChannel.ic;

  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    return ChatMessage(
      id: int.tryParse(json['id']?.toString() ?? '') ?? 0,
      timestamp: DateTime.tryParse(json['timestamp']?.toString() ?? '')?.toLocal() ??
          DateTime.now(),
      direction: json['direction']?.toString() ?? 'incoming',
      channel: ChatChannel.fromValue(json['channel']),
      text: json['text']?.toString() ?? '',
      resynchronized: json['resynchronized'] == true,
    );
  }
}
