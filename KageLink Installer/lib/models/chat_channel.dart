enum ChatChannel {
  ooc,
  ic;

  String get apiValue => name;

  static ChatChannel fromValue(dynamic value) {
    return value?.toString().toLowerCase() == 'ic' ? ChatChannel.ic : ChatChannel.ooc;
  }
}
