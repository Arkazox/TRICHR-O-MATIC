; Windows installer (Inno Setup 6), built by .github/workflows/build-windows.yml:
;   iscc /DAppVersion=X.Y.Z installer\trichrome.iss
; from the PyInstaller folder build in dist\Trichr-o-matic.
;
; Per-user install (no administrator prompt) into
; %LOCALAPPDATA%\Programs\Trichr-o-matic, so the app can update itself:
; trichrome/self_update.py downloads the next version's installer and runs it
; silently with /RELAUNCH=1 once the app has quit.

#ifndef AppVersion
  #error Pass the version: iscc /DAppVersion=X.Y.Z installer\trichrome.iss
#endif

[Setup]
; Never change AppId: it's how a new version finds and replaces the old one.
AppId={{3DE592E1-0878-451D-91E6-5A3F1F2CD027}
AppName=Trichr-o-matic
AppVersion={#AppVersion}
AppVerName=Trichr-o-matic {#AppVersion}
AppPublisher=Simon Jayet
AppPublisherURL=https://github.com/Arkazox/Trichr-o-matic
AppUpdatesURL=https://github.com/Arkazox/Trichr-o-matic/releases
PrivilegesRequired=lowest
DefaultDirName={autopf}\Trichr-o-matic
DisableDirPage=yes
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\resources\icon.ico
UninstallDisplayIcon={app}\Trichr-o-matic.exe
UninstallDisplayName=Trichr-o-matic
OutputDir=..\dist-installer
OutputBaseFilename=Trichr-o-matic-v{#AppVersion}-Windows-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
LicenseFile=..\LICENSE

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; PyInstaller's support files change from one version to the next: clear
; the old ones so nothing stale is left beside the new build.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\Trichr-o-matic\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Trichr-o-matic"; Filename: "{app}\Trichr-o-matic.exe"
Name: "{autodesktop}\Trichr-o-matic"; Filename: "{app}\Trichr-o-matic.exe"; Tasks: desktopicon

[Registry]
; .trirgb sessions open in the app (main.py reads the path from argv).
Root: HKA; Subkey: "Software\Classes\.trirgb"; ValueType: string; ValueName: ""; ValueData: "TrichromaticSession"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\TrichromaticSession"; ValueType: string; ValueName: ""; ValueData: "Trichr-o-matic Session"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\TrichromaticSession\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\Trichr-o-matic.exe,0"
Root: HKA; Subkey: "Software\Classes\TrichromaticSession\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Trichr-o-matic.exe"" ""%1"""

[Run]
; Interactive install: the usual "Launch Trichr-o-matic" checkbox.
Filename: "{app}\Trichr-o-matic.exe"; Description: "{cm:LaunchProgram,Trichr-o-matic}"; Flags: nowait postinstall skipifsilent
; Silent update from the app (/RELAUNCH=1): reopen it once installed.
Filename: "{app}\Trichr-o-matic.exe"; Flags: nowait; Check: IsUpdateRelaunch

[Code]
function IsUpdateRelaunch: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;
