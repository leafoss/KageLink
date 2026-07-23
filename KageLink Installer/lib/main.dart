import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'app.dart';
import 'controllers/session_controller.dart';
import 'localization/locale_controller.dart';
import 'services/profile_repository.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations(const [
    DeviceOrientation.portraitUp,
  ]);

  final sessionController = SessionController(ProfileRepository());
  final localeController = LocaleController();

  await Future.wait([
    sessionController.initialize(),
    localeController.initialize(),
  ]);

  runApp(
    KageLinkApp(
      controller: sessionController,
      localeController: localeController,
    ),
  );
}
