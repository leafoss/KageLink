import 'package:flutter/material.dart';

import 'kage_colors.dart';
import 'kage_spacing.dart';

abstract final class KageDecorations {
  static BoxDecoration get glassPanel => BoxDecoration(
        color: KageColors.charcoal.withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(KageRadius.large),
        border: Border.all(color: KageColors.chakraCyan.withValues(alpha: 0.14)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.35),
            blurRadius: 22,
            offset: const Offset(0, 10),
          ),
        ],
      );

  static BoxDecoration get parchmentPanel => BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [KageColors.parchmentLight, KageColors.parchment],
        ),
        borderRadius: BorderRadius.circular(KageRadius.large),
        border: Border.all(color: KageColors.agedGold.withValues(alpha: 0.9), width: 1.2),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.34),
            blurRadius: 20,
            offset: const Offset(0, 10),
          ),
          BoxShadow(
            color: KageColors.agedGold.withValues(alpha: 0.08),
            blurRadius: 18,
          ),
        ],
      );

  static BoxDecoration get composer => BoxDecoration(
        color: KageColors.charcoal.withValues(alpha: 0.98),
        borderRadius: BorderRadius.circular(KageRadius.large),
        border: Border.all(color: KageColors.chakraCyan.withValues(alpha: 0.2)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.45),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
          BoxShadow(
            color: KageColors.chakraCyan.withValues(alpha: 0.04),
            blurRadius: 16,
          ),
        ],
      );

  static BoxDecoration routeCard({required bool selected}) => BoxDecoration(
        color: selected ? const Color(0xFF202C38) : KageColors.raisedInk.withValues(alpha: 0.96),
        borderRadius: BorderRadius.circular(KageRadius.medium),
        border: Border.all(
          color: selected
              ? KageColors.agedGold.withValues(alpha: 0.95)
              : Colors.white.withValues(alpha: 0.07),
          width: selected ? 1.4 : 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.28),
            blurRadius: 12,
            offset: const Offset(0, 6),
          ),
        ],
      );
}
