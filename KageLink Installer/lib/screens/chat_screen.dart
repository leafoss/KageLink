import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../controllers/game_controls_controller.dart';
import '../controllers/session_controller.dart';
import '../localization/l10n_helpers.dart';
import '../localization/locale_controller.dart';
import '../models/chat_channel.dart';
import '../models/chat_message.dart';
import '../ui/theme/kage_colors.dart';
import '../widgets/chakra_seal.dart';
import '../widgets/chat_composer.dart';
import '../widgets/chat_message_tile.dart';
import '../widgets/scroll_to_latest_button.dart';
import '../widgets/status_badge.dart';
import 'game_screen.dart';
import 'input_calibration_screen.dart';
import 'settings_screen.dart';
import 'stats_screen.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.controller,
    required this.localeController,
  });

  final SessionController controller;
  final LocaleController localeController;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;
  late final GameControlsController _gameControlsController;
  final Map<ChatChannel, TextEditingController> _messageControllers = {
    ChatChannel.ooc: TextEditingController(),
    ChatChannel.ic: TextEditingController(),
  };
  final Map<ChatChannel, ScrollController> _scrollControllers = {
    ChatChannel.ooc: ScrollController(),
    ChatChannel.ic: ScrollController(),
  };
  final Map<ChatChannel, int> _lastMessageCounts = {
    ChatChannel.ooc: 0,
    ChatChannel.ic: 0,
  };
  final Map<ChatChannel, int> _unreadBelow = {
    ChatChannel.ooc: 0,
    ChatChannel.ic: 0,
  };
  final Map<ChatChannel, bool> _nearBottom = {
    ChatChannel.ooc: true,
    ChatChannel.ic: true,
  };

  ChatChannel _activeChannel = ChatChannel.ooc;
  int _activeTabIndex = 0;

  @override
  void initState() {
    super.initState();
    _gameControlsController = GameControlsController();
    _tabController = TabController(length: 4, vsync: this);
    _tabController.addListener(_onTabChanged);
    widget.controller.addListener(_onControllerChanged);

    for (final channel in ChatChannel.values) {
      _lastMessageCounts[channel] = _messagesFor(channel).length;
      _scrollControllers[channel]!.addListener(() => _onScroll(channel));
    }

    WidgetsBinding.instance.addPostFrameCallback((_) {
      for (final channel in ChatChannel.values) {
        _scrollToBottom(channel);
      }
      unawaited(_refreshHistory());
    });
  }

  @override
  void dispose() {
    SystemChrome.setPreferredOrientations(const [DeviceOrientation.portraitUp]);
    widget.controller.removeListener(_onControllerChanged);
    _tabController.removeListener(_onTabChanged);
    _tabController.dispose();
    _gameControlsController.dispose();
    for (final controller in _messageControllers.values) {
      controller.dispose();
    }
    for (final controller in _scrollControllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  List<ChatMessage> _messagesFor(ChatChannel channel) {
    return widget.controller.messages
        .where((message) => message.channel == channel)
        .toList(growable: false);
  }

  Future<void> _refreshHistory() async {
    if (!widget.controller.isConnected) return;
    try {
      await widget.controller.refresh();
      if (mounted) setState(() {});
    } catch (_) {
      // The existing connection/retry flow remains responsible for errors.
    }
  }

  void _onTabChanged() {
    final index = _tabController.index;
    final indexChanged = index != _activeTabIndex;

    if (indexChanged) {
      final leavingRemote = _activeTabIndex >= 2;
      final enteringRemote = index >= 2;

      setState(() {
        _activeTabIndex = index;
        if (!enteringRemote) {
          _activeChannel = ChatChannel.values[index];
          _unreadBelow[_activeChannel] = 0;
        }
      });

      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!enteringRemote && (_nearBottom[_activeChannel] ?? true)) {
          _scrollToBottom(_activeChannel);
        }
      });

      if (leavingRemote && !enteringRemote) {
        FocusManager.instance.primaryFocus?.unfocus();
        unawaited(_refreshHistory());
      }
    }

    // Do not rotate the viewport while TabBarView is still animating between
    // pages. In 3.4.1 the STATS -> GAME transition changed orientation during
    // the 3 -> 2 page animation, which could desynchronize the PageView from
    // the TabController and leave the IC page visible until a second tap.
    if (!_tabController.indexIsChanging) {
      _applyOrientationForTab(index);
    }
  }

  void _applyOrientationForTab(int index) {
    if (index == 2) {
      unawaited(
        SystemChrome.setPreferredOrientations(const [
          DeviceOrientation.landscapeLeft,
          DeviceOrientation.landscapeRight,
        ]),
      );
    } else {
      unawaited(
        SystemChrome.setPreferredOrientations(const [
          DeviceOrientation.portraitUp,
        ]),
      );
    }
  }

  void _onScroll(ChatChannel channel) {
    final scrollController = _scrollControllers[channel]!;
    if (!scrollController.hasClients) return;
    final distanceFromLatest = scrollController.position.pixels -
        scrollController.position.minScrollExtent;
    final near = distanceFromLatest < 88;
    if (near != _nearBottom[channel] ||
        (near && (_unreadBelow[channel] ?? 0) > 0)) {
      setState(() {
        _nearBottom[channel] = near;
        if (near && _activeTabIndex < 2 && channel == _activeChannel) {
          _unreadBelow[channel] = 0;
        }
      });
    }
  }

  void _onControllerChanged() {
    if (!mounted) return;
    var messagesChanged = false;

    for (final channel in ChatChannel.values) {
      final count = _messagesFor(channel).length;
      final previousCount = _lastMessageCounts[channel] ?? 0;
      if (count < previousCount) {
        _lastMessageCounts[channel] = count;
        messagesChanged = true;
        continue;
      }

      final added = count - previousCount;
      if (added <= 0) continue;
      _lastMessageCounts[channel] = count;
      messagesChanged = true;

      final isActive = _activeTabIndex < 2 && channel == _activeChannel;
      if (isActive && (_nearBottom[channel] ?? true)) {
        WidgetsBinding.instance.addPostFrameCallback(
          (_) => _scrollToBottom(channel, animate: true),
        );
      } else {
        _unreadBelow[channel] = (_unreadBelow[channel] ?? 0) + added;
      }
    }

    if (messagesChanged && mounted) {
      setState(() {});
    }
  }

  void _scrollToBottom(ChatChannel channel, {bool animate = false}) {
    final scrollController = _scrollControllers[channel]!;
    if (!scrollController.hasClients) return;
    final target = scrollController.position.minScrollExtent;
    if (animate) {
      scrollController.animateTo(
        target,
        duration: const Duration(milliseconds: 260),
        curve: Curves.easeOutCubic,
      );
    } else {
      scrollController.jumpTo(target);
    }
    if (mounted && (_unreadBelow[channel] ?? 0) > 0) {
      setState(() => _unreadBelow[channel] = 0);
    }
  }

  Future<void> _send() async {
    final channel = _activeChannel;
    final messageController = _messageControllers[channel]!;
    final message = messageController.text.trim();
    if (message.isEmpty) return;

    if (!widget.controller.status.inputFoundFor(channel)) {
      final l10n = context.l10n;
      final errorMessage = channel == ChatChannel.ic
          ? l10n.icInputMissingForSend
          : l10n.oocInputMissingForSend;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(errorMessage)),
      );
      return;
    }

    try {
      if (channel == ChatChannel.ic) {
        await widget.controller.sendIcMessage(message);
      } else {
        await widget.controller.sendOocMessage(message);
      }
      messageController.clear();
      if (!mounted) return;
      FocusScope.of(context).unfocus();
      WidgetsBinding.instance.addPostFrameCallback(
        (_) => _scrollToBottom(channel, animate: true),
      );
    } catch (error) {
      debugPrint('KageLink send error: $error');
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            localizedClientError(
              context.l10n,
              widget.controller.errorMessage,
            ),
          ),
        ),
      );
    }
  }

  Future<void> _handleMenu(String action) async {
    switch (action) {
      case 'refresh':
        try {
          await widget.controller.refresh();
        } catch (_) {}
        break;
      case 'calibrate':
        if (!mounted) return;
        await Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => InputCalibrationScreen(
              controller: widget.controller,
            ),
          ),
        );
        break;
      case 'settings':
        if (!mounted) return;
        await Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => SettingsScreen(
              controller: widget.controller,
              localeController: widget.localeController,
              gameControlsController: _gameControlsController,
            ),
          ),
        );
        break;
      case 'switch':
        await widget.controller.switchServer();
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final controller = widget.controller;
    final profile = controller.activeProfile!;
    final status = controller.status;
    final reconnecting = controller.phase == ConnectionPhase.reconnecting;
    final gameSelected = _activeTabIndex == 2;
    final statsSelected = _activeTabIndex == 3;
    final remoteSelected = gameSelected || statsSelected;

    final pages = <Widget>[
      _buildChannelView(ChatChannel.ooc),
      _buildChannelView(ChatChannel.ic),
      GameScreen(
        profile: profile,
        selected: gameSelected,
        controlsController: _gameControlsController,
      ),
      StatsScreen(
        profile: profile,
        selected: statsSelected,
      ),
    ];

    return Scaffold(
      resizeToAvoidBottomInset: true,
      body: ChakraBackdrop(
        child: SafeArea(
          bottom: false,
          child: Column(
            children: [
              if (remoteSelected)
                _GameNavigationBar(
                  profileName: profile.name,
                  connected: controller.isConnected,
                  reconnecting: reconnecting,
                  controller: _tabController,
                  unreadOoc: _unreadBelow[ChatChannel.ooc] ?? 0,
                  unreadIc: _unreadBelow[ChatChannel.ic] ?? 0,
                  compact: MediaQuery.orientationOf(context) == Orientation.portrait,
                  onMenu: _handleMenu,
                )
              else ...[
                _ChatHeader(
                  profileName: profile.name,
                  address: profile.address,
                  connected: controller.isConnected,
                  reconnecting: reconnecting,
                  onMenu: _handleMenu,
                ),
                _RuntimeStrip(
                  gameOnline: status.gameOnline,
                  chatFound: status.chatFound,
                  oocInputFound: status.oocInputFound,
                  icInputFound: status.icInputFound,
                  summary: reconnecting
                      ? l10n.reconnectingSummary
                      : runtimeSummary(l10n, status),
                ),
                if (controller.errorMessage != null)
                  MaterialBanner(
                    backgroundColor:
                        KageColors.crimsonSeal.withValues(alpha: 0.36),
                    content: Text(
                      localizedClientError(l10n, controller.errorMessage),
                    ),
                    leading: const Icon(
                      Icons.warning_amber_rounded,
                      color: KageColors.warning,
                    ),
                    actions: [
                      TextButton(
                        onPressed: controller.clearError,
                        child: Text(l10n.close),
                      ),
                    ],
                  ),
                _ChannelTabs(
                  controller: _tabController,
                  unreadOoc: _unreadBelow[ChatChannel.ooc] ?? 0,
                  unreadIc: _unreadBelow[ChatChannel.ic] ?? 0,
                ),
              ],
              Expanded(
                child: TabBarView(
                  controller: _tabController,
                  physics: const NeverScrollableScrollPhysics(),
                  children: pages,
                ),
              ),
              if (!remoteSelected) ...[
                _ActiveChannelStrip(channel: _activeChannel),
                ChatComposer(
                  controller: _messageControllers[_activeChannel]!,
                  sending: controller.sending,
                  enabled: controller.isConnected,
                  messageHint: _activeChannel == ChatChannel.ic
                      ? l10n.icMessageHint
                      : l10n.oocMessageHint,
                  disabledHint: l10n.sendingUnavailable,
                  sendTooltip: l10n.sendMessage,
                  onSend: _send,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildChannelView(ChatChannel channel) {
    final l10n = context.l10n;
    final messages = _messagesFor(channel);
    final unread = _unreadBelow[channel] ?? 0;
    final nearBottom = _nearBottom[channel] ?? true;

    return Stack(
      children: [
        if (messages.isEmpty)
          _EmptyChat(channel: channel)
        else
          ListView.builder(
            controller: _scrollControllers[channel],
            reverse: true,
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            padding: const EdgeInsets.fromLTRB(14, 16, 14, 74),
            itemCount: messages.length,
            itemBuilder: (context, index) => ChatMessageTile(
              message: messages[messages.length - 1 - index],
            ),
          ),
        Positioned(
          right: 16,
          bottom: 12,
          child: ScrollToLatestButton(
            visible: !nearBottom,
            unreadCount: unread,
            tooltip: unread > 0
                ? l10n.newMessagesBelow(unread)
                : l10n.scrollToLatest,
            onPressed: () => _scrollToBottom(channel, animate: true),
          ),
        ),
      ],
    );
  }
}


class _GameNavigationBar extends StatelessWidget {
  const _GameNavigationBar({
    required this.profileName,
    required this.connected,
    required this.reconnecting,
    required this.controller,
    required this.unreadOoc,
    required this.unreadIc,
    required this.compact,
    required this.onMenu,
  });

  final String profileName;
  final bool connected;
  final bool reconnecting;
  final TabController controller;
  final int unreadOoc;
  final int unreadIc;
  final bool compact;
  final ValueChanged<String> onMenu;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final navigationHeight = compact ? 44.0 : 48.0;
    final tabHeight = compact ? 42.0 : 46.0;
    return Container(
      height: navigationHeight,
      color: KageColors.charcoal.withValues(alpha: 0.98),
      child: Row(
        children: [
          if (!compact) ...[
            const SizedBox(width: 10),
            const ChakraSeal(size: 31),
            const SizedBox(width: 8),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 150),
              child: Text(
                profileName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ),
            const SizedBox(width: 8),
          ] else
            const SizedBox(width: 4),
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: reconnecting
                  ? KageColors.warning
                  : connected
                      ? KageColors.chakraCyan
                      : KageColors.danger,
            ),
          ),
          SizedBox(width: compact ? 4 : 8),
          Expanded(
            child: TabBar(
              controller: controller,
              indicatorColor: KageColors.emberOrange,
              indicatorWeight: 3,
              labelColor: Colors.white,
              unselectedLabelColor: KageColors.textMuted,
              labelPadding: const EdgeInsets.symmetric(horizontal: 8),
              tabs: [
                _ChannelTab(
                  label: l10n.chatOoc,
                  unread: unreadOoc,
                  height: tabHeight,
                ),
                _ChannelTab(
                  label: l10n.chatIc,
                  unread: unreadIc,
                  height: tabHeight,
                ),
                _ChannelTab(
                  label: 'GAME',
                  unread: 0,
                  height: tabHeight,
                ),
                _ChannelTab(
                  label: l10n.statsTab,
                  unread: 0,
                  height: tabHeight,
                ),
              ],
            ),
          ),
          PopupMenuButton<String>(
            onSelected: onMenu,
            itemBuilder: (context) => [
              PopupMenuItem(
                value: 'refresh',
                child: ListTile(
                  leading: const Icon(Icons.refresh),
                  title: Text(l10n.refreshChat),
                ),
              ),
              PopupMenuItem(
                value: 'settings',
                child: ListTile(
                  leading: const Icon(Icons.settings_outlined),
                  title: Text(l10n.settings),
                ),
              ),
              const PopupMenuDivider(),
              PopupMenuItem(
                value: 'switch',
                child: ListTile(
                  leading: const Icon(Icons.swap_horiz),
                  title: Text(l10n.switchServer),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ChannelTabs extends StatelessWidget {
  const _ChannelTabs({
    required this.controller,
    required this.unreadOoc,
    required this.unreadIc,
  });

  final TabController controller;
  final int unreadOoc;
  final int unreadIc;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Material(
      color: KageColors.charcoal.withValues(alpha: 0.96),
      child: TabBar(
        controller: controller,
        indicatorColor: KageColors.emberOrange,
        indicatorWeight: 3,
        labelColor: Colors.white,
        unselectedLabelColor: KageColors.textMuted,
        tabs: [
          _ChannelTab(label: l10n.chatOoc, unread: unreadOoc),
          _ChannelTab(label: l10n.chatIc, unread: unreadIc),
          const _ChannelTab(label: 'GAME', unread: 0),
          _ChannelTab(label: l10n.statsTab, unread: 0),
        ],
      ),
    );
  }
}

class _ChannelTab extends StatelessWidget {
  const _ChannelTab({
    required this.label,
    required this.unread,
    this.height = 48,
  });

  final String label;
  final int unread;
  final double height;

  @override
  Widget build(BuildContext context) {
    return Tab(
      height: height,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Flexible(
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: Text(
                label,
                style: const TextStyle(fontWeight: FontWeight.w900),
              ),
            ),
          ),
          if (unread > 0) ...[
            const SizedBox(width: 7),
            Container(
              constraints: const BoxConstraints(minWidth: 20, minHeight: 20),
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: const BoxDecoration(
                color: KageColors.crimsonSeal,
                borderRadius: BorderRadius.all(Radius.circular(20)),
              ),
              alignment: Alignment.center,
              child: Text(
                unread > 99 ? '99+' : '$unread',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 10,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _ActiveChannelStrip extends StatelessWidget {
  const _ActiveChannelStrip({required this.channel});

  final ChatChannel channel;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final label = channel == ChatChannel.ic ? l10n.chatIc : l10n.chatOoc;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
      color: channel == ChatChannel.ic
          ? KageColors.crimsonSeal.withValues(alpha: 0.32)
          : KageColors.chakraCyan.withValues(alpha: 0.10),
      child: Text(
        l10n.sendingToChannel(label),
        textAlign: TextAlign.center,
        style: TextStyle(
          color: channel == ChatChannel.ic
              ? KageColors.warning
              : KageColors.chakraCyan,
          fontSize: 11,
          fontWeight: FontWeight.w900,
          letterSpacing: 0.7,
        ),
      ),
    );
  }
}

class _ChatHeader extends StatelessWidget {
  const _ChatHeader({
    required this.profileName,
    required this.address,
    required this.connected,
    required this.reconnecting,
    required this.onMenu,
  });

  final String profileName;
  final String address;
  final bool connected;
  final bool reconnecting;
  final ValueChanged<String> onMenu;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 10, 5, 10),
      decoration: BoxDecoration(
        color: KageColors.charcoal.withValues(alpha: 0.96),
        border: Border(
          bottom: BorderSide(
            color: KageColors.chakraCyan.withValues(alpha: 0.15),
          ),
        ),
      ),
      child: Row(
        children: [
          const ChakraSeal(size: 46),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  profileName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  address,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: KageColors.chakraCyan,
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 116),
            child: StatusBadge(
              label: reconnecting
                  ? l10n.reconnecting
                  : connected
                      ? l10n.connected
                      : l10n.offline,
              active: connected && !reconnecting,
              warning: reconnecting,
            ),
          ),
          PopupMenuButton<String>(
            onSelected: onMenu,
            itemBuilder: (context) => [
              PopupMenuItem(
                value: 'refresh',
                child: ListTile(
                  leading: const Icon(Icons.refresh),
                  title: Text(l10n.refreshChat),
                ),
              ),
              PopupMenuItem(
                value: 'calibrate',
                child: ListTile(
                  leading: const Icon(Icons.tune),
                  title: Text(l10n.calibrateInput),
                ),
              ),
              PopupMenuItem(
                value: 'settings',
                child: ListTile(
                  leading: const Icon(Icons.settings_outlined),
                  title: Text(l10n.settings),
                ),
              ),
              const PopupMenuDivider(),
              PopupMenuItem(
                value: 'switch',
                child: ListTile(
                  leading: const Icon(Icons.swap_horiz),
                  title: Text(l10n.switchServer),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _RuntimeStrip extends StatelessWidget {
  const _RuntimeStrip({
    required this.gameOnline,
    required this.chatFound,
    required this.oocInputFound,
    required this.icInputFound,
    required this.summary,
  });

  final bool gameOnline;
  final bool chatFound;
  final bool oocInputFound;
  final bool icInputFound;
  final String summary;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(8, 9, 8, 10),
      color: KageColors.inkBlack.withValues(alpha: 0.88),
      child: Column(
        children: [
          Row(
            children: [
              Expanded(
                child: _MiniStatus(
                  label: l10n.game,
                  semanticLabel:
                      gameOnline ? l10n.gameLocated : l10n.gameNotLocated,
                  active: gameOnline,
                ),
              ),
              Expanded(
                child: _MiniStatus(
                  label: l10n.reading,
                  semanticLabel:
                      chatFound ? l10n.chatLocated : l10n.chatNotLocated,
                  active: chatFound,
                ),
              ),
              Expanded(
                child: _MiniStatus(
                  label: 'OOC',
                  semanticLabel: oocInputFound
                      ? l10n.oocInputLocated
                      : l10n.oocInputNotLocated,
                  active: oocInputFound,
                ),
              ),
              Expanded(
                child: _MiniStatus(
                  label: 'IC',
                  semanticLabel: icInputFound
                      ? l10n.icInputLocated
                      : l10n.icInputNotLocated,
                  active: icInputFound,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            summary,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: KageColors.textMuted,
              fontSize: 11,
            ),
          ),
        ],
      ),
    );
  }
}

class _MiniStatus extends StatelessWidget {
  const _MiniStatus({
    required this.label,
    required this.semanticLabel,
    required this.active,
  });

  final String label;
  final String semanticLabel;
  final bool active;

  @override
  Widget build(BuildContext context) {
    final color = active ? KageColors.chakraCyan : KageColors.danger;
    return Semantics(
      label: semanticLabel,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            active ? Icons.check_circle : Icons.cancel,
            color: color,
            size: 14,
          ),
          const SizedBox(width: 4),
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: color,
                fontSize: 10,
                fontWeight: FontWeight.w900,
                letterSpacing: 0.6,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _EmptyChat extends StatelessWidget {
  const _EmptyChat({required this.channel});

  final ChatChannel channel;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final isIc = channel == ChatChannel.ic;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(30),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const ChakraSeal(size: 84),
            const SizedBox(height: 16),
            Text(
              isIc ? l10n.emptyIcChatTitle : l10n.emptyOocChatTitle,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w900,
              ),
            ),
            const SizedBox(height: 7),
            Text(
              isIc
                  ? l10n.emptyIcChatDescription
                  : l10n.emptyOocChatDescription,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: KageColors.textMuted,
                height: 1.4,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
