import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../ui/theme/kage_colors.dart';

class GameJoystick extends StatefulWidget {
  const GameJoystick({
    super.key,
    required this.onChanged,
    this.size = 150,
  });

  final ValueChanged<Set<String>> onChanged;
  final double size;

  @override
  State<GameJoystick> createState() => _GameJoystickState();
}

class _GameJoystickState extends State<GameJoystick> {
  int? _pointer;
  Offset _thumb = Offset.zero;
  Set<String> _lastDirections = <String>{};

  void _update(Offset localPosition) {
    final center = Offset(widget.size / 2, widget.size / 2);
    final raw = localPosition - center;
    final radius = widget.size * 0.34;
    final distance = raw.distance;
    final clamped = distance > radius && distance > 0
        ? raw / distance * radius
        : raw;
    final normalizedX = clamped.dx / radius;
    final normalizedY = clamped.dy / radius;
    final directions = <String>{};
    const threshold = 0.32;
    if (normalizedY < -threshold) directions.add('up');
    if (normalizedY > threshold) directions.add('down');
    if (normalizedX < -threshold) directions.add('left');
    if (normalizedX > threshold) directions.add('right');

    setState(() => _thumb = clamped);
    if (!setEquals(directions, _lastDirections)) {
      _lastDirections = directions;
      widget.onChanged(Set<String>.from(directions));
    }
  }

  void _release() {
    _pointer = null;
    setState(() => _thumb = Offset.zero);
    if (_lastDirections.isNotEmpty) {
      _lastDirections = <String>{};
      widget.onChanged(<String>{});
    }
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox.square(
      dimension: widget.size,
      child: Listener(
        behavior: HitTestBehavior.opaque,
        onPointerDown: (event) {
          if (_pointer != null) return;
          _pointer = event.pointer;
          _update(event.localPosition);
        },
        onPointerMove: (event) {
          if (_pointer == event.pointer) _update(event.localPosition);
        },
        onPointerUp: (event) {
          if (_pointer == event.pointer) _release();
        },
        onPointerCancel: (event) {
          if (_pointer == event.pointer) _release();
        },
        child: CustomPaint(
          painter: _JoystickPainter(thumb: _thumb),
        ),
      ),
    );
  }
}

class _JoystickPainter extends CustomPainter {
  const _JoystickPainter({required this.thumb});

  final Offset thumb;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final baseRadius = math.min(size.width, size.height) * 0.46;
    final thumbRadius = baseRadius * 0.31;
    final basePaint = Paint()
      ..color = Colors.white.withValues(alpha: 0.18)
      ..style = PaintingStyle.fill;
    final borderPaint = Paint()
      ..color = Colors.white.withValues(alpha: 0.43)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;
    final accentPaint = Paint()
      ..color = KageColors.chakraCyan.withValues(alpha: 0.34)
      ..style = PaintingStyle.fill;

    canvas.drawCircle(center, baseRadius, basePaint);
    canvas.drawCircle(center, baseRadius, borderPaint);

    const arrowStyle = TextStyle(
      color: Color(0xBFFFFFFF),
      fontSize: 20,
      fontWeight: FontWeight.w900,
    );
    for (final entry in <String, Offset>{
      '▲': Offset(center.dx, center.dy - baseRadius * 0.67),
      '▼': Offset(center.dx, center.dy + baseRadius * 0.67),
      '◀': Offset(center.dx - baseRadius * 0.67, center.dy),
      '▶': Offset(center.dx + baseRadius * 0.67, center.dy),
    }.entries) {
      final painter = TextPainter(
        text: TextSpan(text: entry.key, style: arrowStyle),
        textDirection: TextDirection.ltr,
      )..layout();
      painter.paint(
        canvas,
        entry.value - Offset(painter.width / 2, painter.height / 2),
      );
    }

    canvas.drawCircle(center + thumb, thumbRadius, accentPaint);
    canvas.drawCircle(center + thumb, thumbRadius, borderPaint);
  }

  @override
  bool shouldRepaint(covariant _JoystickPainter oldDelegate) {
    return oldDelegate.thumb != thumb;
  }
}
