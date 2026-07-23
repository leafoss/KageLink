import 'package:flutter/material.dart';

import 'controllers/session_controller.dart';
import 'l10n/app_localizations.dart';
import 'localization/locale_controller.dart';
import 'screens/chat_screen.dart';
import 'screens/server_hub_screen.dart';
import 'ui/theme/kage_theme.dart';

class KageLinkApp extends StatelessWidget {
  const KageLinkApp({
    super.key,
    required this.controller,
    required this.localeController,
  });

  final SessionController controller;
  final LocaleController localeController;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([controller, localeController]),
      builder: (context, _) {
        return MaterialApp(
          onGenerateTitle: (context) => AppLocalizations.of(context).appName,
          debugShowCheckedModeBanner: false,
          theme: KageTheme.dark(),
          locale: localeController.locale,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          localeResolutionCallback: (deviceLocale, supportedLocales) {
            final selected = localeController.locale;
            return supportedLocales.firstWhere(
              (locale) =>
                  locale.languageCode == selected.languageCode &&
                  locale.countryCode == selected.countryCode,
              orElse: () => selected,
            );
          },
          home: controller.activeProfile == null
              ? ServerHubScreen(
                  controller: controller,
                  localeController: localeController,
                )
              : ChatScreen(
                  controller: controller,
                  localeController: localeController,
                ),
        );
      },
    );
  }
}
