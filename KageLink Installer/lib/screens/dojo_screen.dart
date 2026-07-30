import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../localization/l10n_helpers.dart';
import '../models/dojo_status.dart';
import '../models/server_profile.dart';
import '../services/shinobi_api.dart';
import '../ui/theme/kage_colors.dart';

class DojoScreen extends StatefulWidget {
  const DojoScreen({
    super.key,
    required this.profile,
    required this.selected,
  });

  final ServerProfile profile;
  final bool selected;

  @override
  State<DojoScreen> createState() => _DojoScreenState();
}

class _DojoScreenState extends State<DojoScreen> {
  late ShinobiApi _api;
  final TextEditingController _roundsController = TextEditingController(text: '10');
  Timer? _timer;
  DojoStatus? _status;
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
  void didUpdateWidget(covariant DojoScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.profile.address != widget.profile.address ||
        oldWidget.profile.token != widget.profile.token) {
      _api = ShinobiApi(address: widget.profile.address, token: widget.profile.token);
    }
    if (widget.selected && !oldWidget.selected) {
      unawaited(
        SystemChrome.setPreferredOrientations(const [DeviceOrientation.portraitUp]),
      );
      _startPolling();
    } else if (!widget.selected && oldWidget.selected) {
      _stopPolling();
    }
  }

  @override
  void dispose() {
    _stopPolling();
    _roundsController.dispose();
    super.dispose();
  }

  void _startPolling() {
    _timer?.cancel();
    unawaited(_refresh());
    _timer = Timer.periodic(const Duration(milliseconds: 1200), (_) {
      unawaited(_refresh());
    });
  }

  void _stopPolling() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> _refresh() async {
    if (!mounted || !widget.selected || _requestInFlight) return;
    _requestInFlight = true;
    try {
      final status = await _api.fetchDojoStatus();
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
    final rounds = int.tryParse(_roundsController.text.trim());
    if (rounds == null || rounds < 0 || rounds > 999) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(context.l10n.dojoInvalidRounds)),
      );
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final status = await _api.startDojo(rounds: rounds);
      if (!mounted) return;
      setState(() => _status = status);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(context.l10n.dojoStartFailed(error.toString()))),
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
      final status = await _api.stopDojo();
      if (!mounted) return;
      setState(() => _status = status);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(context.l10n.dojoStopFailed(error.toString()))),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _phaseLabel(String phase) {
    final l10n = context.l10n;
    return switch (phase) {
      'starting' => l10n.dojoPhaseStarting,
      'requesting' => l10n.dojoPhaseRequesting,
      'combat' => l10n.dojoPhaseCombat,
      'victory' => l10n.dojoPhaseVictory,
      'recovery' => l10n.dojoPhaseRecovery,
      'ready' => l10n.dojoPhaseReady,
      'stopping' => l10n.dojoPhaseStopping,
      'stopped' => l10n.dojoPhaseStopped,
      'error' => l10n.dojoPhaseError,
      _ => l10n.dojoPhaseIdle,
    };
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
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
            Text(
              l10n.dojoTitle,
              style: const TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w900,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              l10n.dojoDescription,
              style: const TextStyle(color: KageColors.textMuted, height: 1.35),
            ),
            const SizedBox(height: 14),
            _DojoNotice(text: l10n.dojoManualControlsBlocked),
            const SizedBox(height: 10),
            _DojoNotice(text: l10n.dojoEmergencyStop),
            const SizedBox(height: 16),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                _StatusCard(
                  label: l10n.dojoRuntime,
                  value: available ? l10n.dojoInstalled : l10n.dojoNotInstalled,
                  active: available,
                ),
                _StatusCard(
                  label: l10n.dojoPhase,
                  value: _phaseLabel(status?.phase ?? 'idle'),
                  active: running,
                ),
                _StatusCard(
                  label: l10n.dojoProgress,
                  value: l10n.dojoRoundProgress(
                    status?.completedRounds ?? 0,
                    status?.currentRound ?? 0,
                  ),
                  active: running,
                ),
              ],
            ),
            const SizedBox(height: 18),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: KageColors.charcoal,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: KageColors.chakraCyan.withValues(alpha: 0.18),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    l10n.dojoRounds,
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 8),
                  SizedBox(
                    width: 130,
                    child: TextField(
                      controller: _roundsController,
                      enabled: !running && !_busy,
                      keyboardType: TextInputType.number,
                      inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                      decoration: const InputDecoration(
                        border: OutlineInputBorder(),
                        isDense: true,
                      ),
                    ),
                  ),
                  const SizedBox(height: 7),
                  Text(
                    l10n.dojoRoundsHelp,
                    style: const TextStyle(color: KageColors.textMuted),
                  ),
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      Expanded(
                        child: FilledButton.icon(
                          onPressed: available && !running && !_busy ? _start : null,
                          icon: const Icon(Icons.play_arrow_rounded),
                          label: Text(l10n.dojoStart),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: running && !_busy ? _stop : null,
                          icon: const Icon(Icons.stop_circle_outlined),
                          label: Text(l10n.dojoStop),
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
                  Text(
                    l10n.dojoLastEvent,
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
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

class _DojoNotice extends StatelessWidget {
  const _DojoNotice({required this.text});

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

class _StatusCard extends StatelessWidget {
  const _StatusCard({
    required this.label,
    required this.value,
    required this.active,
  });

  final String label;
  final String value;
  final bool active;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 175,
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
          Text(
            label,
            style: const TextStyle(color: KageColors.textMuted, fontSize: 11),
          ),
          const SizedBox(height: 5),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w800)),
        ],
      ),
    );
  }
}
