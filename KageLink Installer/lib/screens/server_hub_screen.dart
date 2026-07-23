import 'package:flutter/material.dart';

import '../controllers/session_controller.dart';
import '../localization/l10n_helpers.dart';
import '../localization/locale_controller.dart';
import '../models/server_profile.dart';
import '../ui/theme/kage_colors.dart';
import '../widgets/chakra_seal.dart';
import '../widgets/kage_loading_indicator.dart';
import '../widgets/language_selector.dart';
import '../widgets/parchment_panel.dart';
import '../widgets/server_profile_card.dart';

class ServerHubScreen extends StatefulWidget {
  const ServerHubScreen({
    super.key,
    required this.controller,
    required this.localeController,
  });

  final SessionController controller;
  final LocaleController localeController;

  @override
  State<ServerHubScreen> createState() => _ServerHubScreenState();
}

class _ServerHubScreenState extends State<ServerHubScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _addressController = TextEditingController();
  final _tokenController = TextEditingController();

  ConnectionKind _kind = ConnectionKind.internal;
  String? _editingId;
  bool _favorite = false;
  bool _obscureToken = true;
  bool _connecting = false;

  @override
  void initState() {
    super.initState();
    if (widget.controller.profiles.isNotEmpty) {
      _assignProfile(widget.controller.profiles.first);
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _addressController.dispose();
    _tokenController.dispose();
    super.dispose();
  }

  String _addressHint(BuildContext context) => switch (_kind) {
        ConnectionKind.internal => context.l10n.networkInternalHint,
        ConnectionKind.external => context.l10n.networkExternalHint,
        ConnectionKind.custom => context.l10n.networkCustomHint,
      };

  void _assignProfile(ServerProfile profile) {
    _editingId = profile.id;
    _nameController.text = profile.name;
    _addressController.text = profile.address;
    _tokenController.text = profile.token;
    _kind = profile.kind;
    _favorite = profile.favorite;
  }

  void _fillProfile(ServerProfile profile) => setState(() => _assignProfile(profile));

  void _newProfile() {
    setState(() {
      _editingId = null;
      _nameController.clear();
      _addressController.clear();
      _tokenController.clear();
      _kind = ConnectionKind.internal;
      _favorite = false;
    });
  }

  Future<void> _connect() async {
    if (!_formKey.currentState!.validate() || _connecting) return;
    FocusScope.of(context).unfocus();
    setState(() => _connecting = true);
    final l10n = context.l10n;

    final profile = ServerProfile(
      id: _editingId ?? ServerProfile.createId(),
      name: _nameController.text.trim().isEmpty ? l10n.defaultRouteName : _nameController.text.trim(),
      address: _addressController.text.trim(),
      token: _tokenController.text.trim(),
      kind: _kind,
      favorite: _favorite,
      lastUsedAt: DateTime.now(),
    );

    try {
      await widget.controller.connect(profile);
    } catch (error) {
      debugPrint('KageLink connection error: $error');
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(localizedClientError(context.l10n, widget.controller.errorMessage))),
      );
    } finally {
      if (mounted) setState(() => _connecting = false);
    }
  }

  Future<void> _deleteProfile(ServerProfile profile) async {
    final l10n = context.l10n;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(l10n.removeRouteTitle),
        content: Text(l10n.removeRouteBody(profile.name)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: Text(l10n.remove)),
        ],
      ),
    );
    if (confirmed != true) return;
    await widget.controller.deleteProfile(profile.id);
    if (_editingId == profile.id) _newProfile();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final profiles = widget.controller.profiles;

    return Scaffold(
      body: ChakraBackdrop(
        child: SafeArea(
          child: CustomScrollView(
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            slivers: [
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 14, 12, 8),
                sliver: SliverToBoxAdapter(
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [LanguageSelector(controller: widget.localeController, compact: true)],
                  ),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 2, 20, 12),
                sliver: SliverToBoxAdapter(
                  child: Column(
                    children: [
                      const ChakraSeal(size: 96),
                      const SizedBox(height: 12),
                      Text(l10n.appName, style: Theme.of(context).textTheme.displaySmall),
                      const SizedBox(height: 5),
                      Text(
                        l10n.appSubtitle.toUpperCase(),
                        style: TextStyle(
                          color: KageColors.chakraCyan.withValues(alpha: 0.85),
                          fontSize: 11,
                          fontWeight: FontWeight.w900,
                          letterSpacing: 2.1,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        l10n.routeHubEyebrow,
                        style: const TextStyle(color: KageColors.agedGold, fontSize: 10, fontWeight: FontWeight.w900, letterSpacing: 1.5),
                      ),
                      const SizedBox(height: 16),
                      ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 540),
                        child: Text(
                          l10n.routeHubDescription,
                          textAlign: TextAlign.center,
                          style: const TextStyle(color: KageColors.textSecondary, height: 1.45),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 10, 16, 24),
                sliver: SliverToBoxAdapter(
                  child: ParchmentPanel(
                    child: Form(
                      key: _formKey,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Expanded(
                                child: Text(
                                  _editingId == null ? l10n.newRoute : l10n.editRoute,
                                  style: const TextStyle(
                                    color: KageColors.textOnParchment,
                                    fontSize: 19,
                                    fontWeight: FontWeight.w900,
                                  ),
                                ),
                              ),
                              IconButton(
                                tooltip: l10n.newAddressTooltip,
                                onPressed: _newProfile,
                                color: const Color(0xFF62452F),
                                icon: const Icon(Icons.add_circle_outline_rounded),
                              ),
                            ],
                          ),
                          const SizedBox(height: 14),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: ConnectionKind.values.map((kind) {
                              final selected = kind == _kind;
                              return ChoiceChip(
                                selected: selected,
                                avatar: Icon(
                                  kind == ConnectionKind.internal
                                      ? Icons.home_work_outlined
                                      : kind == ConnectionKind.external
                                          ? Icons.travel_explore_rounded
                                          : Icons.hub_outlined,
                                  size: 18,
                                  color: selected ? Colors.white : const Color(0xFF4B382A),
                                ),
                                label: Text(connectionKindLabel(l10n, kind)),
                                onSelected: (_) => setState(() => _kind = kind),
                                selectedColor: KageColors.crimsonSeal,
                                backgroundColor: KageColors.parchmentDark,
                                labelStyle: TextStyle(
                                  color: selected ? Colors.white : KageColors.textOnParchment,
                                  fontWeight: FontWeight.w800,
                                ),
                                side: BorderSide.none,
                              );
                            }).toList(growable: false),
                          ),
                          const SizedBox(height: 16),
                          _DarkField(
                            controller: _nameController,
                            label: l10n.routeName,
                            hint: _kind == ConnectionKind.internal ? l10n.routeNameInternalHint : l10n.routeNameExternalHint,
                            icon: Icons.flag_outlined,
                            validator: (_) => null,
                          ),
                          const SizedBox(height: 12),
                          _DarkField(
                            controller: _addressController,
                            label: l10n.serverAddress,
                            hint: _addressHint(context),
                            icon: Icons.hub_outlined,
                            keyboardType: TextInputType.url,
                            validator: (value) => value == null || value.trim().isEmpty ? l10n.addressRequired : null,
                          ),
                          const SizedBox(height: 12),
                          _DarkField(
                            controller: _tokenController,
                            label: l10n.accessToken,
                            hint: l10n.tokenHint,
                            icon: Icons.key_rounded,
                            obscureText: _obscureToken,
                            suffix: IconButton(
                              tooltip: _obscureToken ? l10n.showToken : l10n.hideToken,
                              onPressed: () => setState(() => _obscureToken = !_obscureToken),
                              icon: Icon(_obscureToken ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                            ),
                            validator: (value) => value == null || value.trim().isEmpty ? l10n.tokenRequired : null,
                          ),
                          const SizedBox(height: 8),
                          SwitchListTile.adaptive(
                            contentPadding: EdgeInsets.zero,
                            value: _favorite,
                            activeTrackColor: KageColors.crimsonSeal,
                            title: Text(
                              l10n.favoriteRoute,
                              style: const TextStyle(color: KageColors.textOnParchment, fontWeight: FontWeight.w800),
                            ),
                            subtitle: Text(
                              l10n.favoriteRouteDescription,
                              style: const TextStyle(color: Color(0xFF6C503D)),
                            ),
                            onChanged: (value) => setState(() => _favorite = value),
                          ),
                          const SizedBox(height: 10),
                          SizedBox(
                            width: double.infinity,
                            child: FilledButton.icon(
                              onPressed: _connecting ? null : _connect,
                              icon: _connecting
                                  ? const SizedBox.square(
                                      dimension: 20,
                                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                    )
                                  : const Icon(Icons.link_rounded),
                              label: Text(_connecting ? l10n.openingChannel : l10n.establishChannel),
                            ),
                          ),
                          const SizedBox(height: 11),
                          Text(
                            l10n.addressHelp,
                            style: const TextStyle(color: Color(0xFF6C503D), fontSize: 12, height: 1.35),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 2, 20, 12),
                sliver: SliverToBoxAdapter(
                  child: Row(
                    children: [
                      const Icon(Icons.route_rounded, color: KageColors.agedGold),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(l10n.savedRoutes, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w900)),
                      ),
                      Text(l10n.savedRoutesCount(profiles.length), style: const TextStyle(color: KageColors.chakraCyan)),
                    ],
                  ),
                ),
              ),
              if (widget.controller.loadingProfiles)
                const SliverToBoxAdapter(
                  child: Padding(padding: EdgeInsets.all(36), child: Center(child: KageLoadingIndicator())),
                )
              else if (profiles.isEmpty)
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(20, 4, 20, 36),
                  sliver: SliverToBoxAdapter(
                    child: Container(
                      padding: const EdgeInsets.all(18),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.035),
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
                      ),
                      child: Text(l10n.noSavedRoutes, textAlign: TextAlign.center),
                    ),
                  ),
                )
              else
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 40),
                  sliver: SliverList(
                    delegate: SliverChildBuilderDelegate(
                      (context, index) {
                        if (index.isOdd) return const SizedBox(height: 10);
                        final profile = profiles[index ~/ 2];
                        return ServerProfileCard(
                          profile: profile,
                          selected: profile.id == _editingId,
                          onTap: () => _fillProfile(profile),
                          onConnect: () {
                            _fillProfile(profile);
                            _connect();
                          },
                          onFavorite: () => widget.controller.toggleFavorite(profile.id),
                          onDelete: () => _deleteProfile(profile),
                        );
                      },
                      childCount: profiles.length * 2 - 1,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DarkField extends StatelessWidget {
  const _DarkField({
    required this.controller,
    required this.label,
    required this.hint,
    required this.icon,
    required this.validator,
    this.keyboardType,
    this.obscureText = false,
    this.suffix,
  });

  final TextEditingController controller;
  final String label;
  final String hint;
  final IconData icon;
  final String? Function(String?) validator;
  final TextInputType? keyboardType;
  final bool obscureText;
  final Widget? suffix;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: controller,
      keyboardType: keyboardType,
      obscureText: obscureText,
      autocorrect: false,
      enableSuggestions: !obscureText,
      style: const TextStyle(color: Colors.white),
      decoration: InputDecoration(labelText: label, hintText: hint, prefixIcon: Icon(icon), suffixIcon: suffix),
      validator: validator,
    );
  }
}
