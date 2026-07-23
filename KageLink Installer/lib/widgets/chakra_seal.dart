import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../ui/theme/kage_colors.dart';

class ChakraSeal extends StatelessWidget {
  const ChakraSeal({
    super.key,
    this.size = 72,
    this.glow = true,
  });

  final double size;
  final bool glow;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      image: true,
      label: 'KageLink',
      child: SizedBox.square(
        dimension: size,
        child: CustomPaint(painter: _ChakraSealPainter(glow: glow)),
      ),
    );
  }
}

class _ChakraSealPainter extends CustomPainter {
  const _ChakraSealPainter({required this.glow});

  final bool glow;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.shortestSide / 2;

    if (glow) {
      canvas.drawCircle(
        center,
        radius * 0.8,
        Paint()
          ..color = KageColors.chakraCyan.withValues(alpha: 0.12)
          ..maskFilter = MaskFilter.blur(BlurStyle.normal, radius * 0.3),
      );
      canvas.drawCircle(
        center,
        radius * 0.58,
        Paint()
          ..color = KageColors.crimsonSeal.withValues(alpha: 0.11)
          ..maskFilter = MaskFilter.blur(BlurStyle.normal, radius * 0.25),
      );
    }

    final outer = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = radius * 0.055
      ..color = KageColors.agedGold;
    final chakra = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = radius * 0.07
      ..color = KageColors.chakraCyan;
    final crimson = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = radius * 0.065
      ..color = KageColors.emberOrange;

    canvas.drawCircle(center, radius * 0.83, outer);
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius * 0.64),
      -math.pi * 0.75,
      math.pi * 1.35,
      false,
      chakra,
    );
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius * 0.46),
      math.pi * 0.18,
      math.pi * 1.2,
      false,
      crimson,
    );

    final diamond = Path()
      ..moveTo(center.dx, center.dy - radius * 0.31)
      ..lineTo(center.dx + radius * 0.31, center.dy)
      ..lineTo(center.dx, center.dy + radius * 0.31)
      ..lineTo(center.dx - radius * 0.31, center.dy)
      ..close();
    canvas.drawPath(
      diamond,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = radius * 0.055
        ..color = KageColors.parchment,
    );

    canvas.drawLine(
      Offset(center.dx - radius * 0.22, center.dy + radius * 0.19),
      Offset(center.dx + radius * 0.22, center.dy - radius * 0.19),
      Paint()
        ..strokeCap = StrokeCap.round
        ..strokeWidth = radius * 0.08
        ..color = KageColors.chakraCyan,
    );

    final nodePaint = Paint()..color = KageColors.parchmentLight;
    for (var index = 0; index < 6; index++) {
      final angle = -math.pi / 2 + index * math.pi / 3;
      final point = center + Offset(math.cos(angle), math.sin(angle)) * radius * 0.83;
      canvas.drawCircle(point, radius * 0.052, nodePaint);
    }
    canvas.drawCircle(center, radius * 0.055, nodePaint);
  }

  @override
  bool shouldRepaint(covariant _ChakraSealPainter oldDelegate) => oldDelegate.glow != glow;
}

class ChakraBackdrop extends StatelessWidget {
  const ChakraBackdrop({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: Stack(
        fit: StackFit.expand,
        children: [
          const DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [KageColors.inkBlack, KageColors.nightBlue, KageColors.shadowBlue],
                stops: [0, 0.55, 1],
              ),
            ),
          ),
          IgnorePointer(child: CustomPaint(painter: _BackdropPainter())),
          child,
        ],
      ),
    );
  }
}

class _BackdropPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final inkLine = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..color = KageColors.agedGold.withValues(alpha: 0.055);
    final chakraLine = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..color = KageColors.chakraCyan.withValues(alpha: 0.055);
    final crimsonLine = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2
      ..color = KageColors.crimsonSeal.withValues(alpha: 0.045);

    for (var y = -size.width; y < size.height + size.width; y += 96) {
      canvas.drawLine(Offset(0, y.toDouble()), Offset(size.width, y + size.width), inkLine);
    }

    final topSeal = Offset(size.width * 0.88, size.height * 0.12);
    for (var radius = 72.0; radius < size.width * 0.95; radius += 68) {
      canvas.drawCircle(topSeal, radius, chakraLine);
    }

    final bottomSeal = Offset(size.width * 0.08, size.height * 0.86);
    for (var radius = 46.0; radius < size.width * 0.65; radius += 58) {
      canvas.drawCircle(bottomSeal, radius, crimsonLine);
    }

    final mountain = Path()
      ..moveTo(0, size.height * 0.78)
      ..lineTo(size.width * 0.18, size.height * 0.66)
      ..lineTo(size.width * 0.3, size.height * 0.75)
      ..lineTo(size.width * 0.48, size.height * 0.6)
      ..lineTo(size.width * 0.68, size.height * 0.76)
      ..lineTo(size.width * 0.85, size.height * 0.63)
      ..lineTo(size.width, size.height * 0.74);
    canvas.drawPath(
      mountain,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2
        ..color = Colors.white.withValues(alpha: 0.025),
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
