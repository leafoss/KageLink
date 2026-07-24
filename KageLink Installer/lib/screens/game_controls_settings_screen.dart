import 'dart:async';

import 'package:flutter/material.dart';

import '../controllers/game_controls_controller.dart';
import '../localization/l10n_helpers.dart';
import '../ui/theme/kage_colors.dart';

class GameControlsSettingsScreen extends StatelessWidget {
  const GameControlsSettingsScreen({
    super.key,
    required this.controller,
  });

  final GameControlsController controller;

  Future<void> _confirmResetAll(BuildContext context) async {
    final l10n = context.l10n;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(l10n.restoreAllControls),
        content: Text(l10n.restoreAllControlsConfirmation),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: Text(l10n.cancel),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: Text(l10n.restore),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await controller.resetAll();
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.gameControlsTitle)),
      body: AnimatedBuilder(
        animation: controller,
        builder: (context, _) => ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 36),
          children: [
            Text(
              l10n.gameControlsDescription,
              style: const TextStyle(
                color: KageColors.textMuted,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 18),
            _ControlSetCard(
              title: l10n.buttonSetAbcd,
              buttons: const <String>['A', 'B', 'C', 'D'],
              controller: controller,
              onRestore: () => unawaited(
                controller.resetBank(GameButtonBank.abcd),
              ),
            ),
            const SizedBox(height: 16),
            _ControlSetCard(
              title: l10n.buttonSetZxvu,
              buttons: const <String>['Z', 'X', 'V', 'U'],
              controller: controller,
              onRestore: () => unawaited(
                controller.resetBank(GameButtonBank.zxvu),
              ),
            ),
            const SizedBox(height: 20),
            OutlinedButton.icon(
              onPressed: () => unawaited(_confirmResetAll(context)),
              icon: const Icon(Icons.restart_alt_rounded),
              label: Text(l10n.restoreAllControls),
            ),
            const SizedBox(height: 12),
            Text(
              l10n.gameControlsSecurityNotice,
              style: const TextStyle(
                color: KageColors.textMuted,
                fontSize: 12,
                height: 1.4,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ControlSetCard extends StatelessWidget {
  const _ControlSetCard({
    required this.title,
    required this.buttons,
    required this.controller,
    required this.onRestore,
  });

  final String title;
  final List<String> buttons;
  final GameControlsController controller;
  final VoidCallback onRestore;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Container(
      decoration: BoxDecoration(
        color: KageColors.raisedInk.withValues(alpha: 0.96),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 10, 8),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    title,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                ),
                TextButton.icon(
                  onPressed: onRestore,
                  icon: const Icon(Icons.restore_rounded, size: 18),
                  label: Text(l10n.restoreDefaults),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          for (var index = 0; index < buttons.length; index++) ...[
            _ControlMappingTile(
              button: buttons[index],
              controller: controller,
            ),
            if (index != buttons.length - 1)
              const Divider(height: 1, indent: 16, endIndent: 16),
          ],
        ],
      ),
    );
  }
}

class _ControlMappingTile extends StatelessWidget {
  const _ControlMappingTile({
    required this.button,
    required this.controller,
  });

  final String button;
  final GameControlsController controller;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final current = controller.mappingFor(button);
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      leading: Container(
        width: 42,
        height: 42,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: KageColors.emberOrange.withValues(alpha: 0.20),
          border: Border.all(
            color: KageColors.emberOrange.withValues(alpha: 0.68),
          ),
        ),
        child: Text(
          button,
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900),
        ),
      ),
      title: Text(l10n.gameButtonLabel(button)),
      subtitle: Text(
        l10n.assignedKey(controller.displayLabelForKey(current)),
      ),
      trailing: SizedBox(
        width: 150,
        child: DropdownButtonHideUnderline(
          child: DropdownButton<String>(
            value: current,
            isExpanded: true,
            menuMaxHeight: 360,
            onChanged: (value) {
              if (value == null) return;
              unawaited(controller.setMapping(button, value));
            },
            items: [
              for (final option in GameControlsController.supportedKeys)
                DropdownMenuItem<String>(
                  value: option.id,
                  child: Text(option.label),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
