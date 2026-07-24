#define MyAppName "KageLink PC Agent"
#define MyAppVersion "3.4.1"
#define MyAppPublisher "KageLink"
#define MyAppExeName "KageLink.exe"

[Setup]
AppId={{8D34F502-384A-4F7D-AF3F-4680C930A24A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\KageLink PC Agent
DefaultGroupName=KageLink
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=output
OutputBaseFilename=KageLink-PC-Agent-Setup-v3.4.1
SetupIconFile=assets\kagelink.ico
WizardImageFile=assets\wizard_large.bmp
WizardSmallImageFile=assets\wizard_small.bmp
Compression=lzma2
SolidCompression=yes
ShowLanguageDialog=yes
LanguageDetectionMethod=uilanguage
UninstallDisplayIcon={app}\KageLink.exe
VersionInfoVersion=3.4.1.0
AppMutex=Local\KageLinkPcAgent_v3
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[CustomMessages]
english.StartApp=Open KageLink
english.DesktopShortcut=Create a desktop shortcut
english.RemoveUserData=Do you also want to remove the access key, settings, history, and logs?
english.UninstallApp=Uninstall KageLink
brazilianportuguese.StartApp=Abrir KageLink
brazilianportuguese.DesktopShortcut=Criar um atalho na área de trabalho
brazilianportuguese.RemoveUserData=Deseja remover também a chave de acesso, configurações, histórico e logs?
brazilianportuguese.UninstallApp=Desinstalar KageLink

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
Type: files; Name: "{app}\*.bat"
Type: files; Name: "{app}\app.py"
Type: files; Name: "{app}\requirements.txt"
Type: files; Name: "{app}\ACCESS_TOKEN.txt"
Type: files; Name: "{app}\ENDERECO_EXTERNO_KAGELINK.txt"
Type: files; Name: "{app}\PYTHON_REQUIRED.txt"
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\pc_agent"
Type: filesandordirs; Name: "{app}\web"

[Files]
Source: "build_output\KageLink.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "payload\cloudflared.exe"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "payload\cloudflared.sha256"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "assets\kagelink.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\README.pt-BR.md"; DestDir: "{app}"; DestName: "README_pt-BR.txt"; Flags: ignoreversion
Source: "..\..\README.md"; DestDir: "{app}"; DestName: "README_en-US.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\KageLink"; Filename: "{app}\KageLink.exe"; WorkingDir: "{app}"; IconFilename: "{app}\KageLink.exe"
Name: "{group}\{cm:UninstallApp}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\KageLink"; Filename: "{app}\KageLink.exe"; WorkingDir: "{app}"; IconFilename: "{app}\KageLink.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\KageLink.exe"; WorkingDir: "{app}"; Description: "{cm:StartApp}"; Flags: postinstall nowait skipifsilent runasoriginaluser

[Code]
var
  RemoveDataOnUninstall: Boolean;

function SelectedLanguageTag: String;
begin
  if ActiveLanguage = 'brazilianportuguese' then
    Result := 'pt-BR'
  else
    Result := 'en-US';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SaveStringToFile(ExpandConstant('{app}\install_language.txt'), SelectedLanguageTag, False);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    RemoveDataOnUninstall := MsgBox(ExpandConstant('{cm:RemoveUserData}'), mbConfirmation, MB_YESNO) = IDYES;
  if (CurUninstallStep = usPostUninstall) and RemoveDataOnUninstall then
    DelTree(ExpandConstant('{app}'), True, True, True);
end;
