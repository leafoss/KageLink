import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../controllers/session_controller.dart';
import '../localization/l10n_helpers.dart';
import '../localization/locale_controller.dart';
import 'chat_screen.dart';
import 'dojo_screen.dart';
import 'hunting_screen.dart';

class ConnectedShellV35 extends StatefulWidget {
  const ConnectedShellV35({
    super.key,
    required this.controller,
    required this.localeController,
  });

  final SessionController controller;
  final LocaleController localeController;

  @override
  State<ConnectedShellV35> createState() => _ConnectedShellV35State();
}

class _ConnectedShellV35State extends State<ConnectedShellV35> {
  int _section = 0;

  Future<void> _select(int value) async {
    if (value == _section) return;
    if (value == 1 || value == 2) {
      await SystemChrome.setPreferredOrientations(const [DeviceOrientation.portraitUp]);
    }
    if (!mounted) return;
    setState(() => _section = value);
  }

  @override
  Widget build(BuildContext context) {
    final portrait = MediaQuery.orientationOf(context) == Orientation.portrait;
    final profile = widget.controller.activeProfile!;
    return Scaffold(
      body: IndexedStack(
        index: _section,
        children: [
          ChatScreen(
            controller: widget.controller,
            localeController: widget.localeController,
          ),
          DojoScreen(
            profile: profile,
            selected: _section == 1,
          ),
          HuntingScreen(
            profile: profile,
            selected: _section == 2,
          ),
        ],
      ),
      bottomNavigationBar: portrait
          ? NavigationBar(
              selectedIndex: _section,
              onDestinationSelected: _select,
              destinations: [
                NavigationDestination(
                  icon: const Icon(Icons.hub_outlined),
                  selectedIcon: const Icon(Icons.hub),
                  label: context.l10n.kageLinkSection,
                ),
                NavigationDestination(
                  icon: const Icon(Icons.sports_martial_arts_outlined),
                  selectedIcon: const Icon(Icons.sports_martial_arts),
                  label: context.l10n.dojoTab,
                ),
                const NavigationDestination(
                  icon: Icon(Icons.travel_explore_outlined),
                  selectedIcon: Icon(Icons.travel_explore),
                  label: 'Hunting',
                ),
              ],
            )
          : null,
    );
  }
}
