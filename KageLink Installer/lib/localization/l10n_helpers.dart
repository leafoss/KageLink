import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/runtime_status.dart';
import '../models/server_profile.dart';

extension KageLocalizationsContext on BuildContext {
  AppLocalizations get l10n => AppLocalizations.of(this);
  String get localeTag => Localizations.localeOf(this).toLanguageTag();
}

String connectionKindLabel(AppLocalizations l10n, ConnectionKind kind) {
  return switch (kind) {
    ConnectionKind.internal => l10n.internalNetwork,
    ConnectionKind.external => l10n.externalNetwork,
    ConnectionKind.custom => l10n.customRoute,
  };
}

String connectionKindShortLabel(AppLocalizations l10n, ConnectionKind kind) {
  return switch (kind) {
    ConnectionKind.internal => l10n.internalShort,
    ConnectionKind.external => l10n.externalShort,
    ConnectionKind.custom => l10n.customShort,
  };
}

String runtimeSummary(AppLocalizations l10n, RuntimeStatus status) {
  if (!status.gameOnline) return l10n.gameNotLocated;
  if (!status.chatFound) return l10n.chatNotLocated;
  if (!status.oocInputFound) return l10n.oocUnavailableSummary;
  if (!status.icInputFound) return l10n.icUnavailableSummary;
  return l10n.bothChannelsOperational;
}

String localizedClientError(AppLocalizations l10n, String? rawMessage) {
  final raw = rawMessage?.trim() ?? '';
  final lower = raw.toLowerCase();

  if (lower.contains('ooc_input_not_found')) {
    return l10n.oocInputMissingForSend;
  }
  if (lower.contains('ic_input_not_found')) {
    return l10n.icInputMissingForSend;
  }
  if (lower.contains('game_not_found')) {
    return l10n.gameMissingForSend;
  }
  if (lower.contains('foreground_failed')) {
    return l10n.foregroundFailedForSend;
  }
  if (lower.contains('message_too_long')) {
    return l10n.messageTooLongError;
  }
  if (lower.contains('game_input_truncated') ||
      lower.contains('game_input_write_failed')) {
    return l10n.gameInputTruncatedError;
  }
  if (lower.contains('token') || lower.contains('401')) {
    return l10n.invalidToken;
  }
  if (lower.contains('endereço inválido') ||
      lower.contains('invalid address') ||
      lower.contains('ip ou endereço')) {
    return l10n.invalidAddress;
  }
  if (lower.contains('http://') || lower.contains('https://')) {
    return l10n.httpSchemeRequired;
  }
  if (lower.contains('nenhum servidor') || lower.contains('no server')) {
    return l10n.noServerConnected;
  }
  if (lower.contains('demorou demais') ||
      lower.contains('timeout') ||
      lower.contains('timed out')) {
    return l10n.timeoutError;
  }
  if (lower.contains('connection refused') ||
      lower.contains('socketexception') ||
      lower.contains('não foi possível alcançar') ||
      lower.contains('failed host lookup')) {
    return l10n.unreachableError;
  }
  if (lower.contains('autenticar') || lower.contains('authenticate')) {
    return l10n.authenticationFailed;
  }
  if (lower.contains('histórico') || lower.contains('history')) {
    return l10n.historyFailed;
  }
  if (lower.contains('consultar o servidor') || lower.contains('status')) {
    return l10n.statusFailed;
  }
  if (lower.contains('confirmou') || lower.contains('confirm')) {
    return l10n.sendNotConfirmed;
  }
  if (lower.contains('enviar') || lower.contains('send')) {
    return l10n.sendFailed;
  }
  if (lower.contains('campos de entrada') || lower.contains('input candidates')) {
    return l10n.inputCandidatesFailed;
  }
  if (lower.contains('selecionar o campo') || lower.contains('input preference')) {
    return l10n.inputSelectionFailed;
  }
  if (lower.isEmpty) return l10n.unexpectedError;
  return l10n.serverReportedError;
}
