import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kagelink/services/remote_surface_geometry.dart';

void main() {
  test('vertical Stats window is centered without distortion', () {
    final rect = containedRect(const Size(960, 540), const Size(469, 903));
    expect(rect.height, closeTo(540, 0.001));
    expect(rect.width / rect.height, closeTo(469 / 903, 0.001));
    expect(rect.center, const Offset(480, 270));
  });

  test('points outside letterbox bars are rejected', () {
    const rect = Rect.fromLTWH(340, 0, 280, 540);
    expect(normalizedPointInRect(const Offset(100, 200), rect), isNull);
    expect(normalizedPointInRect(const Offset(480, 270), rect), const Offset(0.5, 0.5));
  });
}
