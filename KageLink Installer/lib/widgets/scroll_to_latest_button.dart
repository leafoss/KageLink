import 'package:flutter/material.dart';

import '../ui/theme/kage_colors.dart';

class ScrollToLatestButton extends StatelessWidget {
  const ScrollToLatestButton({
    super.key,
    required this.visible,
    required this.tooltip,
    required this.onPressed,
    this.unreadCount = 0,
  });

  final bool visible;
  final String tooltip;
  final VoidCallback onPressed;
  final int unreadCount;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      ignoring: !visible,
      child: AnimatedOpacity(
        opacity: visible ? 1 : 0,
        duration: const Duration(milliseconds: 180),
        child: AnimatedScale(
          scale: visible ? 1 : 0.82,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOutCubic,
          child: Semantics(
            button: true,
            label: tooltip,
            child: Tooltip(
              message: tooltip,
              child: Badge(
                isLabelVisible: unreadCount > 0,
                label: Text(unreadCount > 99 ? '99+' : '$unreadCount'),
                backgroundColor: KageColors.crimsonSeal,
                child: Material(
                  color: KageColors.raisedInk,
                  shape: const CircleBorder(),
                  elevation: 8,
                  shadowColor: Colors.black,
                  child: InkWell(
                    customBorder: const CircleBorder(),
                    onTap: onPressed,
                    child: const SizedBox.square(
                      dimension: 50,
                      child: Icon(Icons.keyboard_double_arrow_down_rounded, color: KageColors.chakraCyan),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
