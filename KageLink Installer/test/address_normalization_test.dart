import 'package:flutter_test/flutter_test.dart';
import 'package:kagelink/services/shinobi_api.dart';

void main() {
  test('adds HTTP to a local IP and keeps the port', () {
    final uri = ShinobiApi.normalizeAddress('192.168.0.25:8765');
    expect(uri.scheme, 'http');
    expect(uri.host, '192.168.0.25');
    expect(uri.port, 8765);
  });

  test('accepts an HTTPS address', () {
    final uri = ShinobiApi.normalizeAddress('https://chat.example.com/');
    expect(uri.scheme, 'https');
    expect(uri.host, 'chat.example.com');
  });
}
