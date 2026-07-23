import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../localization/l10n_helpers.dart';
import '../models/chat_message.dart';
import '../ui/theme/kage_colors.dart';

class ChatMessageTile extends StatelessWidget {
  const ChatMessageTile({super.key, required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final outgoing = message.isOutgoing;
    final lower = message.text.toLowerCase();
    final whisper = lower.contains('whisper') || lower.contains('sussurra');
    final system = message.resynchronized || lower.contains('---');
    final time = DateFormat.Hm(context.localeTag).format(message.timestamp);

    final accent = outgoing
        ? KageColors.emberOrange
        : whisper
            ? const Color(0xFF9A78E8)
            : system
                ? KageColors.agedGold
                : KageColors.chakraCyan;

    return Align(
      alignment: outgoing ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.88),
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.fromLTRB(14, 11, 14, 9),
        decoration: BoxDecoration(
          color: outgoing
              ? const Color(0xFF33222A).withValues(alpha: 0.97)
              : KageColors.raisedInk.withValues(alpha: 0.97),
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(17),
            topRight: const Radius.circular(17),
            bottomLeft: Radius.circular(outgoing ? 17 : 5),
            bottomRight: Radius.circular(outgoing ? 5 : 17),
          ),
          border: Border.all(color: accent.withValues(alpha: 0.5)),
          boxShadow: [
            BoxShadow(color: Colors.black.withValues(alpha: 0.28), blurRadius: 10, offset: const Offset(0, 5)),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SelectableText(
              message.text,
              style: const TextStyle(
                color: KageColors.textPrimary,
                fontSize: 14.5,
                height: 1.38,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 7),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(outgoing ? Icons.north_east_rounded : Icons.south_west_rounded, size: 12, color: accent),
                const SizedBox(width: 5),
                Flexible(
                  child: Text(
                    '${outgoing ? l10n.messageOutgoing : l10n.messageIncoming} · $time',
                    style: TextStyle(color: accent.withValues(alpha: 0.9), fontSize: 10.5, fontWeight: FontWeight.w800),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
