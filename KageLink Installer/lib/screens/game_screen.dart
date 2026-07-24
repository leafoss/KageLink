import 'dart:async';

import 'package:flutter/material.dart';

import '../controllers/game_controls_controller.dart';
import '../localization/l10n_helpers.dart';
import '../models/server_profile.dart';
import '../services/game_connection.dart';
import '../ui/theme/kage_colors.dart';
import '../widgets/chakra_seal.dart';
import '../widgets/game_action_button.dart';
import '../widgets/game_joystick.dart';

class GameScreen extends StatefulWidget {
  const GameScreen({
    super.key,
    required this.profile,
    required this.selected,
    required this.controlsController,
  });

  final ServerProfile profile;
  final bool selected;
  final GameControlsController controlsController;

  @override
  State<GameScreen> createState() => GameScreenState();
}

class GameScreenState extends State<GameScreen>
    with AutomaticKeepAliveClientMixin, WidgetsBindingObserver {
  late final GameConnection _connection;
  bool _selected = false;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _selected = widget.selected;
    _connection = GameConnection(widget.profile)..addListener(_refresh);
    widget.controlsController.addListener(_onControlsChanged);
    if (_selected) {
      _connection.setActive(true);
    }
  }

  @override
  void didUpdateWidget(covariant GameScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.selected != widget.selected) {
      setSelected(widget.selected);
    }
    if (oldWidget.controlsController != widget.controlsController) {
      oldWidget.controlsController.removeListener(_onControlsChanged);
      widget.controlsController.addListener(_onControlsChanged);
      _connection.releaseActions();
    }
  }

  void _refresh() {
    if (mounted) setState(() {});
  }

  void _onControlsChanged() {
    _connection.releaseActions();
    if (mounted) setState(() {});
  }

  Future<void> setSelected(bool selected) async {
    _selected = selected;
    await _connection.setActive(selected);
  }

  Future<void> _toggleButtonBank() async {
    _connection.releaseActions();
    await widget.controlsController.toggleBank();
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
    widget.controlsController.removeListener(_onControlsChanged);
    _connection.removeListener(_refresh);
    _connection.dispose();
    super.dispose();
  }

  String _stateTitle(BuildContext context) {
    final l10n = context.l10n;
    return switch (_connection.streamState) {
      GameStreamState.idle => l10n.gameOpenToStart,
      GameStreamState.connecting => l10n.gameConnecting,
      GameStreamState.notFound => l10n.gameNotLocatedTitle,
      GameStreamState.minimized => l10n.gameMinimizedTitle,
      GameStreamState.error => l10n.gameStreamUnavailable,
      GameStreamState.live => l10n.gameLoadingFrame,
    };
  }

  String _stateDescription(BuildContext context) {
    final l10n = context.l10n;
    return switch (_connection.streamState) {
      GameStreamState.notFound => l10n.gameNotLocatedDescription,
      GameStreamState.minimized => l10n.gameMinimizedDescription,
      GameStreamState.error => l10n.gameStreamRetryDescription,
      _ => l10n.gameWaitingAgent,
    };
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final controls = widget.controlsController;
    return ColoredBox(
      color: Colors.black,
      child: Column(
        children: [
          _GameStatusBar(
            live: _connection.isLive,
            controlConnected: _connection.controlActive,
            latencyMs: _connection.latencyMs,
            fps: _connection.fps,
            controlsHidden: _connection.controlsHidden,
            viewMode: _connection.viewMode,
            onToggleControls: _connection.toggleControls,
            onViewModeChanged: _connection.setViewMode,
          ),
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                final shortest = constraints.biggest.shortestSide;
                final joystickSize =
                    (shortest * 0.52).clamp(112.0, 168.0).toDouble();
                final actionSize =
                    (shortest * 0.21).clamp(48.0, 70.0).toDouble();
                return Stack(
                  fit: StackFit.expand,
                  children: [
                    if (_connection.frame != null)
                      Image.memory(
                        _connection.frame!,
                        fit: BoxFit.contain,
                        gaplessPlayback: true,
                        filterQuality: FilterQuality.low,
                      )
                    else
                      _GameUnavailable(
                        title: _stateTitle(context),
                        description: _stateDescription(context),
                      ),
                    if (_connection.isLive &&
                        _connection.controlActive &&
                        !_connection.controlsHidden) ...[
                      Positioned(
                        left: 18,
                        bottom: 14,
                        child: GameJoystick(
                          key: const ValueKey<String>('game-joystick'),
                          size: joystickSize,
                          onChanged: _connection.setMovement,
                        ),
                      ),
                      Positioned(
                        right: 18,
                        bottom: 12,
                        child: _ActionCluster(
                          size: actionSize,
                          bank: controls.activeBank,
                          mappingFor: controls.mappingFor,
                          onAction: _connection.setAction,
                          onToggleBank: () => unawaited(_toggleButtonBank()),
                        ),
                      ),
                    ],
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

class _GameStatusBar extends StatelessWidget {
  const _GameStatusBar({
    required this.live,
    required this.controlConnected,
    required this.latencyMs,
    required this.fps,
    required this.controlsHidden,
    required this.viewMode,
    required this.onToggleControls,
    required this.onViewModeChanged,
  });

  final bool live;
  final bool controlConnected;
  final int? latencyMs;
  final int fps;
  final bool controlsHidden;
  final GameViewMode viewMode;
  final VoidCallback onToggleControls;
  final ValueChanged<GameViewMode> onViewModeChanged;

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
            Icons.network_cell,
            size: 15,
            color:
                controlConnected ? KageColors.success : KageColors.textMuted,
          ),
          const SizedBox(width: 4),
          Text(
            latencyMs == null ? '-- ms' : '$latencyMs ms',
            style: const TextStyle(fontSize: 11),
          ),
          const SizedBox(width: 14),
          Text('$fps fps', style: const TextStyle(fontSize: 11)),
          const Spacer(),
          TextButton.icon(
            onPressed: onToggleControls,
            icon: Icon(
              controlsHidden ? Icons.visibility : Icons.visibility_off,
              size: 16,
            ),
            label: Text(
              controlsHidden
                  ? l10n.gameShowControls
                  : l10n.gameHideControls,
              style: const TextStyle(fontSize: 11),
            ),
          ),
          PopupMenuButton<GameViewMode>(
            tooltip: l10n.gameViewModeTooltip,
            initialValue: viewMode,
            onSelected: onViewModeChanged,
            itemBuilder: (context) => [
              PopupMenuItem(
                value: GameViewMode.full,
                child: Text(l10n.gameFullScreenMode),
              ),
              PopupMenuItem(
                value: GameViewMode.zoom,
                child: Text(l10n.gameZoomMode),
              ),
            ],
            icon: const Icon(Icons.aspect_ratio, size: 19),
          ),
        ],
      ),
    );
  }
}

class _ActionCluster extends StatelessWidget {
  const _ActionCluster({
    required this.size,
    required this.bank,
    required this.mappingFor,
    required this.onAction,
    required this.onToggleBank,
  });

  final double size;
  final GameButtonBank bank;
  final String Function(String button) mappingFor;
  final void Function(String button, String key, bool pressed) onAction;
  final VoidCallback onToggleBank;

  @override
  Widget build(BuildContext context) {
    final gap = size * 0.16;
    final buttons = bank == GameButtonBank.abcd
        ? const <String>['A', 'B', 'C', 'D']
        : const <String>['Z', 'X', 'V', 'U'];
    final top = buttons[0];
    final left = buttons[1];
    final bottom = buttons[2];
    final right = buttons[3];
    final bankLabel = bank == GameButtonBank.abcd ? 'ABCD' : 'ZXVU';

    Widget actionButton(String button) {
      final key = mappingFor(button);
      return GameActionButton(
        key: ValueKey<String>('game-action-$button'),
        label: button,
        size: size,
        onPressedChanged: (pressed) => onAction(button, key, pressed),
      );
    }

    return SizedBox(
      width: size * 3 + gap * 2,
      height: size * 3 + gap * 2,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Positioned(top: 0, left: size + gap, child: actionButton(top)),
          Positioned(left: 0, top: size + gap, child: actionButton(left)),
          Positioned(right: 0, top: size + gap, child: actionButton(right)),
          Positioned(bottom: 0, left: size + gap, child: actionButton(bottom)),
          SizedBox.square(
            dimension: size * 0.82,
            child: Material(
              color: KageColors.inkBlack.withValues(alpha: 0.82),
              shape: CircleBorder(
                side: BorderSide(
                  color: KageColors.agedGold.withValues(alpha: 0.78),
                  width: 1.3,
                ),
              ),
              child: InkWell(
                customBorder: const CircleBorder(),
                onTap: onToggleBank,
                child: Center(
                  child: Text(
                    bankLabel,
                    style: TextStyle(
                      color: KageColors.agedGold,
                      fontSize: (size * 0.17).clamp(9.0, 12.0).toDouble(),
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _GameUnavailable extends StatelessWidget {
  const _GameUnavailable({required this.title, required this.description});

  final String title;
  final String description;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480),
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
            ],
          ),
        ),
      ),
    );
  }
}
