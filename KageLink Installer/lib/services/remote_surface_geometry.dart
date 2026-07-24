import 'dart:math' as math;

import 'package:flutter/widgets.dart';

Rect containedRect(Size container, Size content) {
  if (container.width <= 0 ||
      container.height <= 0 ||
      content.width <= 0 ||
      content.height <= 0) {
    return Rect.zero;
  }
  final scale = math.min(
    container.width / content.width,
    container.height / content.height,
  );
  final width = content.width * scale;
  final height = content.height * scale;
  return Rect.fromLTWH(
    (container.width - width) / 2,
    (container.height - height) / 2,
    width,
    height,
  );
}

Offset? normalizedPointInRect(Offset point, Rect rect) {
  if (rect.isEmpty || !rect.contains(point)) return null;
  return Offset(
    ((point.dx - rect.left) / rect.width).clamp(0.0, 1.0).toDouble(),
    ((point.dy - rect.top) / rect.height).clamp(0.0, 1.0).toDouble(),
  );
}
