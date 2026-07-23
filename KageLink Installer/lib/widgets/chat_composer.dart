import 'package:flutter/material.dart';

import '../ui/theme/kage_colors.dart';
import '../ui/theme/kage_decorations.dart';

class ChatComposer extends StatelessWidget {
  const ChatComposer({
    super.key,
    required this.controller,
    required this.sending,
    required this.enabled,
    required this.messageHint,
    required this.disabledHint,
    required this.sendTooltip,
    required this.onSend,
  });

  final TextEditingController controller;
  final bool sending;
  final bool enabled;
  final String messageHint;
  final String disabledHint;
  final String sendTooltip;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: KageColors.inkBlack.withValues(alpha: 0.88),
      child: SafeArea(
        top: false,
        minimum: const EdgeInsets.fromLTRB(12, 9, 12, 10),
        child: Container(
          padding: const EdgeInsets.fromLTRB(10, 8, 8, 8),
          decoration: KageDecorations.composer,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: TextField(
                  controller: controller,
                  enabled: enabled && !sending,
                  minLines: 1,
                  maxLines: 4,
                  textCapitalization: TextCapitalization.sentences,
                  keyboardType: TextInputType.multiline,
                  textInputAction: TextInputAction.newline,
                  decoration: InputDecoration(
                    hintText: enabled ? messageHint : disabledHint,
                    prefixIcon: const Icon(Icons.edit_note_rounded),
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    disabledBorder: InputBorder.none,
                    filled: false,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 4, vertical: 11),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              ValueListenableBuilder<TextEditingValue>(
                valueListenable: controller,
                builder: (context, value, _) {
                  final canSend = enabled && !sending && value.text.trim().isNotEmpty;
                  return Semantics(
                    button: true,
                    enabled: canSend,
                    label: sendTooltip,
                    child: Tooltip(
                      message: sendTooltip,
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 160),
                        width: 54,
                        height: 54,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          boxShadow: canSend
                              ? [
                                  BoxShadow(
                                    color: KageColors.emberOrange.withValues(alpha: 0.32),
                                    blurRadius: 16,
                                  ),
                                ]
                              : const [],
                        ),
                        child: FilledButton(
                          onPressed: canSend ? onSend : null,
                          style: FilledButton.styleFrom(
                            padding: EdgeInsets.zero,
                            shape: const CircleBorder(),
                            backgroundColor: KageColors.emberOrange,
                            disabledBackgroundColor: KageColors.raisedInk,
                          ),
                          child: sending
                              ? const SizedBox.square(
                                  dimension: 21,
                                  child: CircularProgressIndicator(strokeWidth: 2.2, color: Colors.white),
                                )
                              : const Icon(Icons.near_me_rounded, size: 24),
                        ),
                      ),
                    ),
                  );
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}
