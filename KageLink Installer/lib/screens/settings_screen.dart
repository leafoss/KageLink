import 'package:flutter/material.dart';

import '../controllers/game_controls_controller.dart';
import '../controllers/session_controller.dart';
import '../localization/l10n_helpers.dart';
import '../localization/locale_controller.dart';
import '../services/primary_character_service.dart';
import '../ui/theme/kage_colors.dart';
import '../widgets/chakra_seal.dart';
import '../widgets/language_selector.dart';
import 'game_controls_settings_screen.dart';
import 'input_calibration_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({
    super.key,
    required this.controller,
    required this.localeController,
    required this.gameControlsController,
  });

  final SessionController controller;
  final LocaleController localeController;
  final GameControlsController gameControlsController;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  PrimaryCharacterSetting? _characterSetting;
  bool _loadingCharacter = false;

  bool get _isPortuguese => Localizations.localeOf(context).languageCode == 'pt';

  PrimaryCharacterService? get _characterService {
    final profile = widget.controller.activeProfile;
    return profile == null ? null : PrimaryCharacterService(profile);
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadPrimaryCharacter());
  }

  Future<void> _loadPrimaryCharacter() async {
    final service = _characterService;
    if (service == null || _loadingCharacter) return;
    setState(() => _loadingCharacter = true);
    try {
      final setting = await service.fetch();
      if (mounted) setState(() => _characterSetting = setting);
    } catch (_) {
      // The setting remains editable even if the first read fails.
    } finally {
      if (mounted) setState(() => _loadingCharacter = false);
    }
  }

  Future<void> _editPrimaryCharacter() async {
    final service = _characterService;
    if (service == null) return;

    if (_characterSetting == null) {
      try {
        _characterSetting = await service.fetch();
      } catch (_) {}
    }
    if (!mounted) return;

    final textController = TextEditingController(
      text: _characterSetting?.primaryCharacter ?? '',
    );
    final saved = _characterSetting?.savedCharacters ?? const <String>[];
    final isPt = _isPortuguese;

    final shouldSave = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(isPt ? 'Personagem principal' : 'Primary character'),
        content: SizedBox(
          width: 420,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                isPt
                    ? 'Informe o personagem que o LeafOS deve considerar como seu personagem nesta sessão.'
                    : 'Choose the character LeafOS should treat as your character for this session.',
              ),
              const SizedBox(height: 14),
              TextField(
                controller: textController,
                autofocus: true,
                maxLength: 160,
                textInputAction: TextInputAction.done,
                decoration: InputDecoration(
                  labelText: isPt ? 'Nome do personagem' : 'Character name',
                  hintText: 'Matsunaya Hika',
                ),
                onSubmitted: (_) => Navigator.of(dialogContext).pop(true),
              ),
              if (saved.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  isPt ? 'Personagens salvos' : 'Saved characters',
                  style: Theme.of(context).textTheme.labelLarge,
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  children: [
                    for (final name in saved)
                      ActionChip(
                        label: Text(name),
                        onPressed: () {
                          textController
                            ..text = name
                            ..selection = TextSelection.collapsed(offset: name.length);
                        },
                      ),
                  ],
                ),
              ],
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: Text(context.l10n.cancel),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: Text(isPt ? 'Salvar' : 'Save'),
          ),
        ],
      ),
    );

    if (shouldSave != true) {
      textController.dispose();
      return;
    }

    final name = textController.text.trim();
    textController.dispose();
    try {
      final setting = await service.save(name);
      if (!mounted) return;
      setState(() => _characterSetting = setting);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            name.isEmpty
                ? (isPt ? 'Personagem principal removido.' : 'Primary character cleared.')
                : (isPt ? 'Personagem principal salvo: $name' : 'Primary character saved: $name'),
          ),
        ),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.toString())),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final controller = widget.controller;
    final profile = controller.activeProfile;
    final status = controller.status;
    final secure = profile?.address.toLowerCase().startsWith('https://') == true;
    final isPt = _isPortuguese;
    final character = _characterSetting?.primaryCharacter ?? '';

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
            _SettingsCard(child: LanguageSelector(controller: widget.localeController)),
            const SizedBox(height: 22),
            _SectionTitle(
              icon: Icons.person_outline_rounded,
              title: isPt ? 'Personagem' : 'Character',
            ),
            _SettingsCard(
              child: ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.badge_outlined, color: KageColors.chakraCyan),
                title: Text(isPt ? 'Personagem principal' : 'Primary character'),
                subtitle: Text(
                  _loadingCharacter
                      ? (isPt ? 'Carregando...' : 'Loading...')
                      : character.isNotEmpty
                          ? character
                          : (isPt ? 'Nenhum personagem configurado' : 'No character configured'),
                ),
                trailing: const Icon(Icons.edit_outlined),
                onTap: profile == null ? null : _editPrimaryCharacter,
              ),
            ),
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
            _SectionTitle(
              icon: Icons.sports_esports_rounded,
              title: l10n.gameControlsTitle,
            ),
            _SettingsCard(
              child: ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(
                  Icons.gamepad_outlined,
                  color: KageColors.emberOrange,
                ),
                title: Text(l10n.gameControlsTitle),
                subtitle: Text(l10n.gameControlsSettingsSubtitle),
                trailing: const Icon(Icons.chevron_right_rounded),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => GameControlsSettingsScreen(
                      controller: widget.gameControlsController,
                    ),
                  ),
                ),
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
