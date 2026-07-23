import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../localization/l10n_helpers.dart';
import '../models/server_profile.dart';
import '../ui/theme/kage_colors.dart';
import '../ui/theme/kage_decorations.dart';

class ServerProfileCard extends StatelessWidget {
  const ServerProfileCard({
    super.key,
    required this.profile,
    required this.selected,
    required this.onTap,
    required this.onConnect,
    required this.onFavorite,
    required this.onDelete,
  });

  final ServerProfile profile;
  final bool selected;
  final VoidCallback onTap;
  final VoidCallback onConnect;
  final VoidCallback onFavorite;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final date = DateFormat.yMd(context.localeTag).add_Hm().format(profile.lastUsedAt.toLocal());
    final secure = profile.address.trimLeft().toLowerCase().startsWith('https://');
    final internal = profile.kind == ConnectionKind.internal;
    final accent = internal ? KageColors.chakraCyan : KageColors.emberOrange;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.fromLTRB(14, 13, 6, 13),
          decoration: KageDecorations.routeCard(selected: selected),
          child: Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: 0.1),
                  shape: BoxShape.circle,
                  border: Border.all(color: accent.withValues(alpha: 0.35)),
                ),
                child: Icon(internal ? Icons.home_work_outlined : Icons.travel_explore_rounded, color: accent),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            profile.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 15.5),
                          ),
                        ),
                        const SizedBox(width: 7),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: accent.withValues(alpha: 0.09),
                            borderRadius: BorderRadius.circular(999),
                          ),
                          child: Text(
                            connectionKindShortLabel(l10n, profile.kind),
                            style: TextStyle(fontSize: 10, color: accent, fontWeight: FontWeight.w800),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 5),
                    Text(
                      profile.address,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: KageColors.chakraCyan, fontSize: 12),
                    ),
                    const SizedBox(height: 4),
                    Wrap(
                      spacing: 8,
                      runSpacing: 4,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        Text(l10n.lastUsed(date), style: const TextStyle(color: KageColors.textMuted, fontSize: 10.5)),
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(secure ? Icons.verified_user_outlined : Icons.info_outline, size: 12, color: secure ? KageColors.success : KageColors.warning),
                            const SizedBox(width: 3),
                            Text(
                              secure ? l10n.httpsProtected : l10n.httpUnencrypted,
                              style: TextStyle(fontSize: 10, color: secure ? KageColors.success : KageColors.warning),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              IconButton(
                tooltip: profile.favorite ? l10n.removeFavorite : l10n.favorite,
                onPressed: onFavorite,
                icon: Icon(
                  profile.favorite ? Icons.auto_awesome_rounded : Icons.auto_awesome_outlined,
                  color: profile.favorite ? KageColors.agedGold : KageColors.textMuted,
                ),
              ),
              PopupMenuButton<String>(
                onSelected: (value) {
                  if (value == 'connect') onConnect();
                  if (value == 'delete') onDelete();
                },
                itemBuilder: (context) => [
                  PopupMenuItem(value: 'connect', child: ListTile(leading: const Icon(Icons.link_rounded), title: Text(l10n.connectNow))),
                  PopupMenuItem(value: 'delete', child: ListTile(leading: const Icon(Icons.delete_outline_rounded), title: Text(l10n.delete))),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
