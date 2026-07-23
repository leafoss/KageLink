import 'package:flutter/material.dart';

import '../localization/l10n_helpers.dart';
import '../localization/locale_controller.dart';
import '../ui/theme/kage_colors.dart';

class LanguageSelector extends StatelessWidget {
  const LanguageSelector({
    super.key,
    required this.controller,
    this.compact = false,
  });

  final LocaleController controller;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final selected = controller.locale.languageCode == 'en' ? 'en' : 'pt';

    if (compact) {
      return Semantics(
        button: true,
        label: l10n.selectLanguage,
        child: PopupMenuButton<String>(
          tooltip: l10n.selectLanguage,
          initialValue: selected,
          icon: const Icon(Icons.translate_rounded, color: KageColors.parchment),
          onSelected: (value) => controller.setLocale(
            value == 'en' ? const Locale('en', 'US') : const Locale('pt', 'BR'),
          ),
          itemBuilder: (context) => [
            PopupMenuItem(value: 'pt', child: Text(l10n.portugueseBrazil)),
            PopupMenuItem(value: 'en', child: Text(l10n.englishUS)),
          ],
        ),
      );
    }

    return SegmentedButton<String>(
      showSelectedIcon: false,
      segments: [
        ButtonSegment(value: 'pt', label: Text(l10n.portugueseBrazil), icon: const Icon(Icons.language_rounded)),
        ButtonSegment(value: 'en', label: Text(l10n.englishUS), icon: const Icon(Icons.public_rounded)),
      ],
      selected: {selected},
      onSelectionChanged: (values) {
        final value = values.first;
        controller.setLocale(value == 'en' ? const Locale('en', 'US') : const Locale('pt', 'BR'));
      },
    );
  }
}
