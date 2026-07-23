import 'package:flutter/material.dart';

import '../controllers/session_controller.dart';
import '../localization/l10n_helpers.dart';
import '../localization/locale_controller.dart';
import '../ui/theme/kage_colors.dart';
import '../widgets/chakra_seal.dart';
import '../widgets/language_selector.dart';
import 'input_calibration_screen.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({
    super.key,
    required this.controller,
    required this.localeController,
  });

  final SessionController controller;
  final LocaleController localeController;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final profile = controller.activeProfile;
    final status = controller.status;
    final secure = profile?.address.toLowerCase().startsWith('https://') == true;

    return Scaffold(
      appBar: AppBar(title: Text(l10n.settingsTitle)),
      body: ChakraBackdrop(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 36),
          children: [
            _SectionTitle(icon: Icons.route_rounded, title: l10n.connectionSection),
            _SettingsCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const ChakraSeal(size: 48, glow: false),
                    title: Text(profile?.name ?? l10n.unknown),
                    subtitle: Text(profile?.address ?? l10n.unknown, maxLines: 2, overflow: TextOverflow.ellipsis),
                    trailing: Icon(secure ? Icons.verified_user_outlined : Icons.info_outline, color: secure ? KageColors.success : KageColors.warning),
                  ),
                  const Divider(),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(status.fullyOperational ? Icons.check_circle_outline_rounded : Icons.warning_amber_rounded, color: status.fullyOperational ? KageColors.success : KageColors.warning),
                    title: Text(status.fullyOperational ? l10n.agentOperational : l10n.agentAttention),
                    subtitle: Text(runtimeSummary(l10n, status)),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 22),
            _SectionTitle(icon: Icons.translate_rounded, title: l10n.languageSection),
            _SettingsCard(child: LanguageSelector(controller: localeController)),
            const SizedBox(height: 22),
            _SectionTitle(icon: Icons.auto_awesome_rounded, title: l10n.appearanceSection),
            _SettingsCard(
              child: ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.dark_mode_outlined, color: KageColors.chakraCyan),
                title: Text(l10n.visualTheme),
                subtitle: Text(l10n.chakraNight),
              ),
            ),
            const SizedBox(height: 22),
            _SectionTitle(icon: Icons.tune_rounded, title: l10n.calibrationSection),
            _SettingsCard(
              child: Column(
                children: [
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.keyboard_alt_outlined, color: KageColors.agedGold),
                    title: Text(l10n.openCalibration),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => InputCalibrationScreen(controller: controller)),
                    ),
                  ),
                  const Divider(),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.swap_horiz_rounded, color: KageColors.emberOrange),
                    title: Text(l10n.changeRoute),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () async {
                      await controller.switchServer();
                      if (context.mounted) Navigator.of(context).popUntil((route) => route.isFirst);
                    },
                  ),
                ],
              ),
            ),
            const SizedBox(height: 22),
            _SectionTitle(icon: Icons.info_outline_rounded, title: l10n.aboutSection),
            _SettingsCard(
              child: ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Image.asset('assets/kagelink_mark.png', width: 52, height: 52),
                title: Text(l10n.appName, style: const TextStyle(fontWeight: FontWeight.w900)),
                subtitle: Text(l10n.versionLabel),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.icon, required this.title});

  final IconData icon;
  final String title;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 0, 4, 9),
      child: Row(
        children: [
          Icon(icon, size: 19, color: KageColors.agedGold),
          const SizedBox(width: 8),
          Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w900)),
        ],
      ),
    );
  }
}

class _SettingsCard extends StatelessWidget {
  const _SettingsCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: KageColors.raisedInk.withValues(alpha: 0.96),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: child,
    );
  }
}
