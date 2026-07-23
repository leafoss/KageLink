import 'package:flutter/material.dart';

import 'kage_colors.dart';
import 'kage_spacing.dart';

abstract final class KageTheme {
  static ThemeData dark() {
    final colorScheme = ColorScheme.fromSeed(
      seedColor: KageColors.chakraCyan,
      brightness: Brightness.dark,
      primary: KageColors.chakraCyan,
      secondary: KageColors.emberOrange,
      tertiary: KageColors.agedGold,
      surface: KageColors.charcoal,
      error: KageColors.danger,
    );

    final outline = OutlineInputBorder(
      borderRadius: BorderRadius.circular(KageRadius.medium),
      borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.1)),
    );

    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: KageColors.inkBlack,
      fontFamily: 'sans-serif',
      visualDensity: VisualDensity.standard,
      splashFactory: InkSparkle.splashFactory,
      textTheme: const TextTheme(
        displaySmall: TextStyle(
          color: KageColors.parchment,
          fontSize: 34,
          fontWeight: FontWeight.w900,
          letterSpacing: 0.4,
        ),
        headlineSmall: TextStyle(
          color: KageColors.textPrimary,
          fontWeight: FontWeight.w900,
          letterSpacing: 0.2,
        ),
        titleLarge: TextStyle(color: KageColors.textPrimary, fontWeight: FontWeight.w900),
        titleMedium: TextStyle(color: KageColors.textPrimary, fontWeight: FontWeight.w800),
        bodyLarge: TextStyle(color: KageColors.textPrimary, height: 1.4),
        bodyMedium: TextStyle(color: KageColors.textSecondary, height: 1.38),
        labelLarge: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 0.35),
        labelSmall: TextStyle(color: KageColors.textMuted, fontWeight: FontWeight.w700),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: KageColors.charcoal,
        foregroundColor: KageColors.textPrimary,
        centerTitle: false,
        elevation: 0,
        scrolledUnderElevation: 0,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: KageColors.inkBlack.withValues(alpha: 0.78),
        labelStyle: const TextStyle(color: KageColors.textSecondary),
        hintStyle: const TextStyle(color: KageColors.textMuted),
        border: outline,
        enabledBorder: outline,
        disabledBorder: outline.copyWith(
          borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.05)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(KageRadius.medium),
          borderSide: const BorderSide(color: KageColors.chakraCyan, width: 1.5),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(KageRadius.medium),
          borderSide: const BorderSide(color: KageColors.danger),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: KageColors.emberOrange,
          foregroundColor: Colors.white,
          minimumSize: const Size(48, 52),
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 13),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(KageRadius.medium)),
          textStyle: const TextStyle(fontWeight: FontWeight.w900, letterSpacing: 0.35),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: KageColors.chakraCyan,
          minimumSize: const Size(48, 48),
          side: BorderSide(color: KageColors.chakraCyan.withValues(alpha: 0.38)),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(KageRadius.medium)),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(foregroundColor: KageColors.chakraCyan),
      ),
      cardTheme: CardThemeData(
        color: KageColors.raisedInk,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(KageRadius.medium)),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: KageColors.charcoal,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(KageRadius.large)),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: KageColors.charcoal,
        showDragHandle: true,
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: KageColors.raisedInk,
        contentTextStyle: const TextStyle(color: KageColors.textPrimary),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(KageRadius.medium)),
        behavior: SnackBarBehavior.floating,
      ),
      popupMenuTheme: PopupMenuThemeData(
        color: KageColors.raisedInk,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(KageRadius.medium)),
      ),
      dividerTheme: DividerThemeData(color: Colors.white.withValues(alpha: 0.08), thickness: 1),
    );
  }
}
