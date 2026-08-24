import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/hunting_status.dart';
import '../models/server_profile.dart';
import '../services/hunting_api.dart';
import '../services/shinobi_api.dart';
import '../ui/theme/kage_colors.dart';

class HuntingScreen extends StatefulWidget {
  const HuntingScreen({
    super.key,
    required this.profile,
    required this.selected,
  });

  final ServerProfile profile;
  final bool selected;

  @override
  State<HuntingScreen> createState() => _HuntingScreenState();
}

class _HuntingScreenState extends State<HuntingScreen> {
  late ShinobiApi _api;
  Timer? _timer;
  HuntingStatus? _status;
  String? _error;
  bool _busy = false;
  bool _requestInFlight = false;

  @override
  void initState() {
    super.initState();
    _api = ShinobiApi(address: widget.profile.address, token: widget.profile.token);
    if (widget.selected) _startPolling();
  }

  @override
  void didUpdateWidget(covariant HuntingScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.profile.address != widget.profile.address ||
        oldWidget.profile.token != widget.profile.token) {
      _api = ShinobiApi(address: widget.profile.address, token: widget.profile.token);
    }
    if (widget.selected && !oldWidget.selected) {
      unawaited(SystemChrome.setPreferredOrientations(const [DeviceOrientation.portraitUp]));
      _startPolling();
    } else if (!widget.selected && oldWidget.selected) {
      _stopPolling();
    }
  }

  @override
  void dispose() {
    _stopPolling();
    // IndexedStack keeps this screen alive while changing tabs. Disposal means the
    // connected shell/profile is leaving, so autonomous input is stopped safely.
    if (_status?.running ?? false) {
      unawaited(_api.stopHunting());
    }
    super.dispose();
  }

  void _startPolling() {
    _timer?.cancel();
    unawaited(_refresh());
    _timer = Timer.periodic(const Duration(milliseconds: 1200), (_) => unawaited(_refresh()));
  }

  void _stopPolling() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> _refresh() async {
    if (!mounted || !widget.selected || _requestInFlight) return;
    _requestInFlight = true;
    try {
      final status = await _api.fetchHuntingStatus();
      if (!mounted) return;
      setState(() {
        _status = status;
        _error = null;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      _requestInFlight = false;
    }
  }

  Future<void> _start() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final status = await _api.startHunting();
      if (!mounted) return;
      setState(() => _status = status);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Não foi possível iniciar Hunting: $error')),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _stop() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final status = await _api.stopHunting();
      if (!mounted) return;
      setState(() => _status = status);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _phase(String value) => switch (value) {
        'starting' => 'Iniciando',
        'searching' => 'Procurando',
        'acquiring' => 'Identificando inimigo',
        'combat' => 'Combate',
        'recovery' => 'Recuperação',
        'stopping' => 'Parando',
        'stopped' => 'Parado',
        'error' => 'Erro',
        _ => 'Inativo',
      };

  String _percent(double? value) => value == null ? '—' : '${(value * 100).round()}%';

  @override
  Widget build(BuildContext context) {
    final status = _status;
    final running = status?.running ?? false;
    final available = status?.available ?? false;
    final lastEvent = (_error ?? status?.lastEvent ?? '').trim();

    return ColoredBox(
      color: KageColors.voidBlack,
      child: SafeArea(
        top: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
          children: [
            const Text(
              'Hunting',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: 6),
            const Text(
              'Patrulha automática da floresta. Anda para cima e para baixo, reage somente à frase exata de emboscada e usa o mesmo combate Alpha 6 do Dojo.',
              style: TextStyle(color: KageColors.textMuted, height: 1.35),
            ),
            const SizedBox(height: 14),
            const _Notice(
              text: 'Sem a frase “Clã, Nome dashes from above the trees as they prepare their ambush.” nenhum corpo recebe autoridade de ataque.',
            ),
            const SizedBox(height: 10),
            const _Notice(
              text: 'F12 ou STOP soltam os controles. Trocar de aba não interrompe Hunting.',
            ),
            const SizedBox(height: 16),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                _StatusCard(label: 'Runtime', value: available ? 'Instalado' : 'Indisponível', active: available),
                _StatusCard(label: 'Estado', value: _phase(status?.phase ?? 'idle'), active: running),
                _StatusCard(label: 'Vitórias', value: '${status?.kills ?? 0}', active: running),
                _StatusCard(label: 'Direção', value: (status?.direction ?? '-').toUpperCase(), active: running),
                _StatusCard(label: 'HP', value: _percent(status?.health), active: status?.phase == 'recovery'),
                _StatusCard(label: 'Stamina', value: _percent(status?.stamina), active: status?.staminaCalibrated ?? false),
              ],
            ),
            const SizedBox(height: 16),
            if (!(status?.staminaCalibrated ?? false))
              const _Warning(
                text: 'Stamina ainda não possui leitor visual calibrado no KageLink. Após uma vitória o bot aperta V e permanece em recuperação de forma segura, sem usar Chakra como substituto. O próximo log/screenshot permitirá calibrar essa última leitura.',
              ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: KageColors.charcoal,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: KageColors.chakraCyan.withValues(alpha: 0.18)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Último inimigo: ${status?.lastEnemy.trim().isNotEmpty == true ? status!.lastEnemy : '—'}'),
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      Expanded(
                        child: FilledButton.icon(
                          onPressed: available && !running && !_busy ? _start : null,
                          icon: const Icon(Icons.travel_explore),
                          label: const Text('START HUNTING'),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: running && !_busy ? _stop : null,
                          icon: const Icon(Icons.stop_circle_outlined),
                          label: const Text('STOP'),
                        ),
                      ),
                    ],
                  ),
                  if (_busy) ...[
                    const SizedBox(height: 12),
                    const LinearProgressIndicator(),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 16),
            Container(
              constraints: const BoxConstraints(minHeight: 130),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: KageColors.charcoal,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: KageColors.emberOrange.withValues(alpha: 0.22)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Último evento', style: TextStyle(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 10),
                  SelectableText(
                    lastEvent.isEmpty ? '—' : lastEvent,
                    style: TextStyle(
                      color: _error == null ? KageColors.textMuted : KageColors.warning,
                      fontFamily: 'monospace',
                      height: 1.35,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Notice extends StatelessWidget {
  const _Notice({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: KageColors.chakraCyan.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: KageColors.chakraCyan.withValues(alpha: 0.18)),
      ),
      child: Text(text, style: const TextStyle(color: KageColors.textMuted)),
    );
  }
}

class _Warning extends StatelessWidget {
  const _Warning({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: KageColors.emberOrange.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: KageColors.emberOrange.withValues(alpha: 0.40)),
      ),
      child: Text(text, style: const TextStyle(color: KageColors.textMuted)),
    );
  }
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.label, required this.value, required this.active});
  final String label;
  final String value;
  final bool active;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 160,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: KageColors.charcoal,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: active
              ? KageColors.chakraCyan.withValues(alpha: 0.55)
              : KageColors.textMuted.withValues(alpha: 0.16),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: KageColors.textMuted, fontSize: 11)),
          const SizedBox(height: 5),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w800)),
        ],
      ),
    );
  }
}
