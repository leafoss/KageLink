import 'package:flutter/material.dart';

import '../ui/theme/kage_colors.dart';
import 'chakra_seal.dart';

class KageLoadingIndicator extends StatefulWidget {
  const KageLoadingIndicator({super.key, this.label});

  final String? label;

  @override
  State<KageLoadingIndicator> createState() => _KageLoadingIndicatorState();
}

class _KageLoadingIndicatorState extends State<KageLoadingIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(milliseconds: 1400))..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final disableAnimations = MediaQuery.disableAnimationsOf(context);
    final seal = const ChakraSeal(size: 54, glow: false);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        disableAnimations
            ? seal
            : RotationTransition(turns: _controller, child: seal),
        if (widget.label != null) ...[
          const SizedBox(height: 12),
          Text(widget.label!, style: const TextStyle(color: KageColors.textSecondary)),
        ],
      ],
    );
  }
}
