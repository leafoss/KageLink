import 'package:flutter/material.dart';

import '../localization/l10n_helpers.dart';
import '../models/server_profile.dart';
import '../services/remote_surface_geometry.dart';
import '../services/stats_connection.dart';
import '../ui/theme/kage_colors.dart';
import '../widgets/chakra_seal.dart';

class StatsScreen extends StatefulWidget {
  const StatsScreen({
    super.key,
    required this.profile,
    required this.selected,
  });

  final ServerProfile profile;
  final bool selected;

  @override
  State<StatsScreen> createState() => StatsScreenState();
}

class StatsScreenState extends State<StatsScreen>
    with AutomaticKeepAliveClientMixin, WidgetsBindingObserver {
  late final StatsConnection _connection;
  bool _selected = false;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _selected = widget.selected;
    _connection = StatsConnection(widget.profile)..addListener(_refresh);
    if (_selected) {
      _connection.setActive(true);
    }
  }

  @override
  void didUpdateWidget(covariant StatsScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.selected != widget.selected) {
      setSelected(widget.selected);
    }
  }

  void _refresh() {
    if (mounted) setState(() {});
  }

  Future<void> setSelected(bool selected) async {
    _selected = selected;
    await _connection.setActive(selected);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _selected) {
      _connection.setActive(true);
    } else if (state != AppLifecycleState.resumed) {
      _connection.setActive(false);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _connection.removeListener(_refresh);
    _connection.dispose();
    super.dispose();
  }

  String _stateTitle(BuildContext context) {
    final l10n = context.l10n;
    return switch (_connection.streamState) {
      StatsStreamState.idle => l10n.statsOpenToStart,
      StatsStreamState.connecting => l10n.statsConnecting,
      StatsStreamState.notFound => l10n.statsWindowNotOpenTitle,
      StatsStreamState.minimized => l10n.statsWindowMinimizedTitle,
      StatsStreamState.error => l10n.statsStreamUnavailable,
      StatsStreamState.live => l10n.statsLoadingFrame,
    };
  }

  String _stateDescription(BuildContext context) {
    final l10n = context.l10n;
    return switch (_connection.streamState) {
      StatsStreamState.notFound => l10n.statsWindowNotOpenDescription,
      StatsStreamState.minimized => l10n.statsWindowMinimizedDescription,
      StatsStreamState.error => l10n.statsRetryDescription,
      _ => l10n.statsWaitingAgent,
    };
  }


  void _sendPointerClick(Offset localPosition, Size renderedSize, String button) {
    final normalized = normalizedPointInRect(
      localPosition,
      Offset.zero & renderedSize,
    );
    if (normalized == null) return;
    _connection.sendClick(
      x: normalized.dx,
      y: normalized.dy,
      button: button,
    );
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final dimensionsReady =
        _connection.frameWidth > 0 && _connection.frameHeight > 0;
    return ColoredBox(
      color: Colors.black,
      child: Column(
        children: [
          _StatsStatusBar(
            live: _connection.isLive,
            controlConnected: _connection.controlActive,
            latencyMs: _connection.latencyMs,
            fps: _connection.fps,
            onRetry: _connection.requestOpen,
          ),
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                if (_connection.frame == null || !dimensionsReady) {
                  return _StatsUnavailable(
                    title: _stateTitle(context),
                    description: _stateDescription(context),
                    onRetry: _connection.requestOpen,
                  );
                }

                final rect = containedRect(
                  constraints.biggest,
                  Size(
                    _connection.frameWidth.toDouble(),
                    _connection.frameHeight.toDouble(),
                  ),
                );
                return Stack(
                  fit: StackFit.expand,
                  children: [
                    Positioned.fromRect(
                      rect: rect,
                      child: GestureDetector(
                        behavior: HitTestBehavior.opaque,
                        onTapUp: (details) => _sendPointerClick(
                          details.localPosition,
                          rect.size,
                          'left',
                        ),
                        onLongPressStart: (details) => _sendPointerClick(
                          details.localPosition,
                          rect.size,
                          'right',
                        ),
                        child: Image.memory(
                          _connection.frame!,
                          fit: BoxFit.fill,
                          gaplessPlayback: true,
                          filterQuality: FilterQuality.low,
                        ),
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _StatsStatusBar extends StatelessWidget {
  const _StatsStatusBar({
    required this.live,
    required this.controlConnected,
    required this.latencyMs,
    required this.fps,
    required this.onRetry,
  });

  final bool live;
  final bool controlConnected;
  final int? latencyMs;
  final int fps;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Container(
      height: 42,
      padding: const EdgeInsets.symmetric(horizontal: 10),
      color: KageColors.inkBlack.withValues(alpha: 0.96),
      child: Row(
        children: [
          Icon(
            Icons.circle,
            size: 10,
            color: live ? Colors.redAccent : KageColors.textMuted,
          ),
          const SizedBox(width: 6),
          Text(
            live ? l10n.gameLive : l10n.gameOffline,
            style: TextStyle(
              color: live ? Colors.redAccent : KageColors.textMuted,
              fontSize: 11,
              fontWeight: FontWeight.w900,
            ),
          ),
          const SizedBox(width: 14),
          Icon(
            Icons.touch_app_outlined,
            size: 16,
            color:
                controlConnected ? KageColors.success : KageColors.textMuted,
          ),
          const SizedBox(width: 5),
          Text(
            latencyMs == null ? '-- ms' : '$latencyMs ms',
            style: const TextStyle(fontSize: 11),
          ),
          const SizedBox(width: 14),
          Text('$fps fps', style: const TextStyle(fontSize: 11)),
          const Spacer(),
          TextButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh_rounded, size: 17),
            label: Text(
              l10n.tryAgain,
              style: const TextStyle(fontSize: 11),
            ),
          ),
        ],
      ),
    );
  }
}

class _StatsUnavailable extends StatelessWidget {
  const _StatsUnavailable({
    required this.title,
    required this.description,
    required this.onRetry,
  });

  final String title;
  final String description;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 500),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const ChakraSeal(size: 74),
              const SizedBox(height: 14),
              Text(
                title,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w900,
                ),
              ),
              const SizedBox(height: 7),
              Text(
                description,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: KageColors.textMuted,
                  height: 1.35,
                ),
              ),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh_rounded),
                label: Text(l10n.tryAgain),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
