import 'package:flutter/material.dart';

import '../ui/theme/kage_colors.dart';

class GameActionButton extends StatefulWidget {
  const GameActionButton({
    super.key,
    required this.label,
    required this.onPressedChanged,
    this.size = 64,
  });

  final String label;
  final ValueChanged<bool> onPressedChanged;
  final double size;

  @override
  State<GameActionButton> createState() => _GameActionButtonState();
}

class _GameActionButtonState extends State<GameActionButton> {
  final Set<int> _pointers = <int>{};

  void _down(PointerDownEvent event) {
    final wasEmpty = _pointers.isEmpty;
    _pointers.add(event.pointer);
    if (wasEmpty) widget.onPressedChanged(true);
    setState(() {});
  }

  void _up(PointerEvent event) {
    if (!_pointers.remove(event.pointer)) return;
    if (_pointers.isEmpty) widget.onPressedChanged(false);
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final pressed = _pointers.isNotEmpty;
    return SizedBox.square(
      dimension: widget.size,
      child: Listener(
        behavior: HitTestBehavior.opaque,
        onPointerDown: _down,
        onPointerUp: _up,
        onPointerCancel: _up,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 80),
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: pressed
                ? KageColors.emberOrange.withValues(alpha: 0.42)
                : Colors.white.withValues(alpha: 0.18),
            border: Border.all(
              color: pressed
                  ? KageColors.emberOrange.withValues(alpha: 0.92)
                  : Colors.white.withValues(alpha: 0.50),
              width: 1.5,
            ),
            boxShadow: pressed
                ? [
                    BoxShadow(
                      color: KageColors.emberOrange.withValues(alpha: 0.28),
                      blurRadius: 12,
                    ),
                  ]
                : null,
          ),
          alignment: Alignment.center,
          child: Text(
            widget.label,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.w900,
            ),
          ),
        ),
      ),
    );
  }
}
