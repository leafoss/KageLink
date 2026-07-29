import 'package:flutter_test/flutter_test.dart';
import 'package:kagelink/models/dojo_status.dart';

void main() {
  test('parses Dojo runtime status and prioritizes errors', () {
    final status = DojoStatus.fromJson({
      'available': true,
      'running': true,
      'phase': 'combat',
      'current_round': 4,
      'completed_rounds': 3,
      'last_line': 'LIVE MELEE',
      'last_error': 'FOREGROUND_LOST',
      'return_code': null,
    });

    expect(status.available, isTrue);
    expect(status.running, isTrue);
    expect(status.phase, 'combat');
    expect(status.currentRound, 4);
    expect(status.completedRounds, 3);
    expect(status.lastEvent, 'FOREGROUND_LOST');
  });

  test('accepts numeric strings from compatible agents', () {
    final status = DojoStatus.fromJson({
      'current_round': '7',
      'completed_rounds': '6',
      'return_code': '0',
    });

    expect(status.currentRound, 7);
    expect(status.completedRounds, 6);
    expect(status.returnCode, 0);
    expect(status.phase, 'idle');
  });
}
