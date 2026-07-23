import 'package:flutter/material.dart';

import '../controllers/session_controller.dart';
import '../localization/l10n_helpers.dart';
import '../models/chat_channel.dart';
import '../models/runtime_status.dart';
import '../ui/theme/kage_colors.dart';
import '../widgets/chakra_seal.dart';
import '../widgets/kage_loading_indicator.dart';

class InputCalibrationScreen extends StatefulWidget {
  const InputCalibrationScreen({super.key, required this.controller});

  final SessionController controller;

  @override
  State<InputCalibrationScreen> createState() => _InputCalibrationScreenState();
}

class _InputCalibrationScreenState extends State<InputCalibrationScreen> {
  late Future<InputCandidateResult> _future;
  String? _savingKey;

  @override
  void initState() {
    super.initState();
    _future = widget.controller.fetchInputCandidates();
  }

  void _reload() =>
      setState(() => _future = widget.controller.fetchInputCandidates());

  Future<void> _select(
    InputCandidate candidate,
    ChatChannel channel,
  ) async {
    final key = '${channel.apiValue}:${candidate.hwnd}';
    setState(() => _savingKey = key);
    try {
      await widget.controller.selectInputCandidate(candidate, channel);
      if (!mounted) return;
      final channelLabel =
          channel == ChatChannel.ic ? context.l10n.chatIc : context.l10n.chatOoc;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            context.l10n.inputSelectedForChannel(
              channelLabel,
              candidate.width,
              candidate.height,
            ),
          ),
        ),
      );
      _reload();
    } catch (error) {
      debugPrint('KageLink calibration error: $error');
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            localizedClientError(context.l10n, error.toString()),
          ),
        ),
      );
    } finally {
      if (mounted) setState(() => _savingKey = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.calibrationTitle),
        actions: [
          IconButton(
            tooltip: l10n.refreshChat,
            onPressed: _reload,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: ChakraBackdrop(
        child: FutureBuilder<InputCandidateResult>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const Center(child: KageLoadingIndicator());
            }
            if (snapshot.hasError) {
              return _CalibrationError(
                message: localizedClientError(
                  l10n,
                  snapshot.error.toString(),
                ),
                onRetry: _reload,
              );
            }

            final result = snapshot.data!;
            if (result.candidates.isEmpty) {
              return _CalibrationError(
                message: l10n.noInputControls,
                onRetry: _reload,
              );
            }

            final oocPreference = result.preferenceFor(ChatChannel.ooc);
            final icPreference = result.preferenceFor(ChatChannel.ic);
            final icHasSavedGeometry = icPreference.preferredWidth > 0 &&
                icPreference.preferredHeight > 0;

            return ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: KageColors.raisedInk.withValues(alpha: 0.96),
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(
                      color: KageColors.chakraCyan.withValues(alpha: 0.2),
                    ),
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const ChakraSeal(size: 52, glow: false),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Text(
                          l10n.calibrationIntroDual,
                          style: const TextStyle(height: 1.4),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                _CalibrationStatus(
                  oocConfigured: result.candidates.any(oocPreference.matches),
                  icConfigured: icHasSavedGeometry &&
                      result.candidates.any(
                        (candidate) =>
                            icPreference.matches(candidate) &&
                            !oocPreference.matches(candidate),
                      ),
                ),
                const SizedBox(height: 14),
                ...result.candidates.map((candidate) {
                  final selectedOoc = oocPreference.matches(candidate);
                  final selectedIc = icHasSavedGeometry &&
                      icPreference.matches(candidate) &&
                      !selectedOoc;
                  return _CandidateCard(
                    candidate: candidate,
                    selectedOoc: selectedOoc,
                    selectedIc: selectedIc,
                    savingOoc:
                        _savingKey == 'ooc:${candidate.hwnd}',
                    savingIc: _savingKey == 'ic:${candidate.hwnd}',
                    onSelectOoc: () =>
                        _select(candidate, ChatChannel.ooc),
                    onSelectIc: () =>
                        _select(candidate, ChatChannel.ic),
                  );
                }),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _CalibrationStatus extends StatelessWidget {
  const _CalibrationStatus({
    required this.oocConfigured,
    required this.icConfigured,
  });

  final bool oocConfigured;
  final bool icConfigured;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Row(
      children: [
        Expanded(
          child: _StatusChip(
            label: 'OOC',
            configured: oocConfigured,
            configuredText: l10n.located,
            missingText: l10n.notLocated,
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: _StatusChip(
            label: 'IC',
            configured: icConfigured,
            configuredText: l10n.located,
            missingText: l10n.notLocated,
          ),
        ),
      ],
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({
    required this.label,
    required this.configured,
    required this.configuredText,
    required this.missingText,
  });

  final String label;
  final bool configured;
  final String configuredText;
  final String missingText;

  @override
  Widget build(BuildContext context) {
    final color = configured ? KageColors.success : KageColors.warning;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            configured ? Icons.check_circle : Icons.warning_amber_rounded,
            size: 16,
            color: color,
          ),
          const SizedBox(width: 7),
          Flexible(
            child: Text(
              '$label: ${configured ? configuredText : missingText}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: color,
                fontSize: 11,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _CandidateCard extends StatelessWidget {
  const _CandidateCard({
    required this.candidate,
    required this.selectedOoc,
    required this.selectedIc,
    required this.savingOoc,
    required this.savingIc,
    required this.onSelectOoc,
    required this.onSelectIc,
  });

  final InputCandidate candidate;
  final bool selectedOoc;
  final bool selectedIc;
  final bool savingOoc;
  final bool savingIc;
  final VoidCallback onSelectOoc;
  final VoidCallback onSelectIc;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final selected = selectedOoc || selectedIc;
    final highCompatibility = candidate.width >= 500 &&
        candidate.height >= 40 &&
        candidate.height <= 70;

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      color: selected ? const Color(0xFF24303B) : KageColors.raisedInk,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(
          color: selected ? KageColors.agedGold : Colors.white10,
          width: selected ? 1.4 : 1,
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Container(
                  width: 48,
                  height: 48,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: KageColors.chakraCyan.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Text(
                    candidate.index.toString().padLeft(3, '0'),
                    style: const TextStyle(
                      color: KageColors.chakraCyan,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        l10n.channelNumber(candidate.index),
                        style: const TextStyle(
                          fontWeight: FontWeight.w900,
                          fontSize: 16,
                        ),
                      ),
                      const SizedBox(height: 5),
                      Text(
                        '${l10n.classLabel}: Edit',
                        style: const TextStyle(
                          color: KageColors.textSecondary,
                          fontSize: 12,
                        ),
                      ),
                      Text(
                        '${l10n.dimensions}: ${candidate.width} × ${candidate.height}',
                        style: const TextStyle(
                          color: KageColors.textSecondary,
                          fontSize: 12,
                        ),
                      ),
                      Text(
                        '${l10n.visible}: ${candidate.visible ? l10n.yes : l10n.no} · '
                        '${l10n.enabled}: ${candidate.enabled ? l10n.yes : l10n.no}',
                        style: const TextStyle(
                          color: KageColors.textSecondary,
                          fontSize: 12,
                        ),
                      ),
                      Text(
                        l10n.relativePosition(
                          candidate.relativeLeft,
                          candidate.relativeTop,
                        ),
                        style: const TextStyle(
                          color: KageColors.textMuted,
                          fontSize: 11,
                        ),
                      ),
                      const SizedBox(height: 5),
                      Text(
                        highCompatibility
                            ? l10n.compatibilityHigh
                            : l10n.compatibilityStandard,
                        style: TextStyle(
                          color: highCompatibility
                              ? KageColors.success
                              : KageColors.warning,
                          fontSize: 11,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: selectedOoc || selectedIc || savingOoc
                        ? null
                        : onSelectOoc,
                    child: savingOoc
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : Text(
                            selectedOoc ? l10n.activeOoc : l10n.useAsOoc,
                          ),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: FilledButton(
                    onPressed: selectedIc || selectedOoc || savingIc
                        ? null
                        : onSelectIc,
                    child: savingIc
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : Text(selectedIc ? l10n.activeIc : l10n.useAsIc),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _CalibrationError extends StatelessWidget {
  const _CalibrationError({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.warning_amber_rounded,
              size: 52,
              color: KageColors.warning,
            ),
            const SizedBox(height: 14),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(height: 1.4),
            ),
            const SizedBox(height: 18),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: Text(context.l10n.retry),
            ),
          ],
        ),
      ),
    );
  }
}
